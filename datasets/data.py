# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# pylint: skip-file
""" data iterator for mnist """
import os
import random
import logging
import zipfile

logging.basicConfig(level=logging.INFO)

import mxnet as mx
from mxnet.test_utils import download


def get_cifar10(dir="data"):
    """Downloads CIFAR10 dataset into a directory in the current directory with the name `data`,
    and then extracts all files into the directory `data/cifar`.
    """
    if not os.path.isdir(dir):
        os.makedirs(dir)
    if (not os.path.exists(os.path.join(dir, 'cifar', 'train.rec'))) or \
            (not os.path.exists(os.path.join(dir, 'cifar', 'test.rec'))) or \
            (not os.path.exists(os.path.join(dir, 'cifar', 'train.lst'))) or \
            (not os.path.exists(os.path.join(dir, 'cifar', 'test.lst'))):
        zip_file_path = download('http://data.mxnet.io/mxnet/data/cifar10.zip',
                                 dirname=dir)
        with zipfile.ZipFile(zip_file_path) as zf:
            zf.extractall(dir)


def as_kwargs(**kwargs):
    return kwargs


def get_augmented_train_val(batch_size, data_shape, resize=-1, num_parts=1, part_index=0, dir=None, aug_level=1,
                            mean_subtraction=False, num_workers=4, dtype=None, train_path=("cifar", "train.rec"),
                            val_path=("cifar", "test.rec")):
    kwargs = as_kwargs(
        resize=resize,
        rand_crop=False,
        rand_mirror=False,
        data_shape=data_shape,
        batch_size=batch_size,
        num_parts=num_parts,
        part_index=part_index,
        preprocess_threads=num_workers,
        dtype=dtype
    )
    train_kwargs = as_kwargs(path_imgrec=os.path.join(dir, *train_path))
    train_kwargs.update(kwargs)

    val_kwargs = as_kwargs(path_imgrec=os.path.join(dir, *val_path))
    val_kwargs.update(kwargs)

    if aug_level >= 1:
        train_kwargs.update(as_kwargs(rand_crop=True, rand_mirror=True))
    if aug_level >= 2:
        train_kwargs.update(as_kwargs(random_h=36, random_s=50, random_l=50))
    if aug_level >= 3:
        train_kwargs.update(as_kwargs(max_rotate_angle=10, max_shear_ratio=0.1, max_aspect_ratio=0.25))
    if mean_subtraction:
        rgb_mean = '123.68,116.779,103.939'
        rgb_mean = [float(i) for i in rgb_mean.split(',')]
        mean_args = as_kwargs(mean_r=rgb_mean[0], mean_g=rgb_mean[1], mean_b=rgb_mean[2])
        train_kwargs.update(mean_args)
        val_kwargs.update(mean_args)

    return mx.io.ImageRecordIter(**train_kwargs), mx.io.ImageRecordIter(**val_kwargs)


def get_cifar10_iterator(batch_size, data_shape, resize=-1, num_parts=1, part_index=0, dir=None,
                         aug_level=1, mean_subtraction=False):
    get_cifar10(dir=dir)

    return get_augmented_train_val(batch_size, data_shape, resize=resize, num_parts=num_parts, part_index=part_index,
                                   dir=dir, aug_level=aug_level, mean_subtraction=mean_subtraction)


def get_imagenet_iterator(root, batch_size, num_workers, data_shape=224, dtype='float32',
                         aug_level=1, mean_subtraction=False):
    return get_augmented_train_val(batch_size, (3, data_shape, data_shape), resize=-1, num_parts=1, part_index=0,
                                   dir=root, aug_level=aug_level, mean_subtraction=mean_subtraction,
                                   num_workers=num_workers, dtype=dtype, train_path=("imagenet1k-train.rec",),
                                   val_path=("imagenet1k-val.rec",))


class DummyIter(mx.io.DataIter):
    def __init__(self, batch_size, data_shape, batches=100):
        super(DummyIter, self).__init__(batch_size)
        self.data_shape = (batch_size,) + data_shape
        self.label_shape = (batch_size,)
        self.provide_data = [('data', self.data_shape)]
        self.provide_label = [('softmax_label', self.label_shape)]
        self.batch = mx.io.DataBatch(data=[mx.nd.zeros(self.data_shape)],
                                     label=[mx.nd.zeros(self.label_shape)])
        self._batches = 0
        self.batches = batches

    def next(self):
        if self._batches < self.batches:
            self._batches += 1
            return self.batch
        else:
            self._batches = 0
            raise StopIteration


def dummy_iterator(batch_size, data_shape):
    return DummyIter(batch_size, data_shape), DummyIter(batch_size, data_shape)


class ImagePairIter(mx.io.DataIter):
    def __init__(self, path, data_shape, label_shape, batch_size=64, flag=0, input_aug=None, target_aug=None):
        super(ImagePairIter, self).__init__(batch_size)
        self.data_shape = (batch_size,) + data_shape
        self.label_shape = (batch_size,) + label_shape
        self.input_aug = input_aug
        self.target_aug = target_aug
        self.provide_data = [('data', self.data_shape)]
        self.provide_label = [('label', self.label_shape)]
        is_image_file = lambda fn: any(fn.endswith(ext) for ext in [".png", ".jpg", ".jpeg"])
        self.filenames = [os.path.join(path, x) for x in os.listdir(path) if is_image_file(x)]
        self.count = 0
        self.flag = flag
        random.shuffle(self.filenames)

    def next(self):
        from PIL import Image
        if self.count + self.batch_size <= len(self.filenames):
            data = []
            label = []
            for i in range(self.batch_size):
                fn = self.filenames[self.count]
                self.count += 1
                image = Image.open(fn).convert('YCbCr').split()[0]
                if image.size[0] > image.size[1]:
                    image = image.transpose(Image.TRANSPOSE)
                image = mx.nd.expand_dims(mx.nd.array(image), axis=2)
                target = image.copy()
                for aug in self.input_aug:
                    image = aug(image)
                for aug in self.target_aug:
                    target = aug(target)
                data.append(image)
                label.append(target)

            data = mx.nd.concat(*[mx.nd.expand_dims(d, axis=0) for d in data], dim=0)
            label = mx.nd.concat(*[mx.nd.expand_dims(d, axis=0) for d in label], dim=0)
            data = [mx.nd.transpose(data, axes=(0, 3, 1, 2)).astype('float32') / 255]
            label = [mx.nd.transpose(label, axes=(0, 3, 1, 2)).astype('float32') / 255]

            return mx.io.DataBatch(data=data, label=label)
        else:
            raise StopIteration

    def reset(self):
        self.count = 0
        random.shuffle(self.filenames)
