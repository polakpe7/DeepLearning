#!/usr/bin/env python3
# 55d46f86-b962-11e7-a937-00505601122b
# 4fc059fa-abd2-11e7-a937-00505601122b
# be28f437-a9b0-11e7-a937-00505601122b
import tensorflow as tf
import numpy as np
from keras import backend as K
import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.layers import Dense, Activation, Flatten, Dropout, BatchNormalization, concatenate, Input, add, UpSampling2D
from tensorflow.keras.layers import Conv2D, MaxPooling2D, AveragePooling2D
from tensorflow.keras import regularizers
from tensorflow.keras.callbacks import LearningRateScheduler
from keras.models import load_model

from fashion_masks_data import FashionMasks

# TODO: Define a suitable model in the Network class.
# A suitable starting model contains some number of shared
# convolutional layers, followed by two heads, one predicting
# the label and the other one the masks.
class Network(tf.keras.Model):

    def block(self, input, size, dropout, regularization, pool = True):

        x = Conv2D(size, (3,3), padding='same', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(input)

        x = BatchNormalization()(x)
        x = Conv2D(size, (3,3), padding='same', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(x)

        x = concatenate([x,input])
        x = BatchNormalization()(x)

        if pool:
            x = MaxPooling2D(pool_size=(2,2), padding='valid')(x)
        x = Dropout(dropout)(x)

        return x
    
    def __init__(self, args):
        input_img = Input(shape = (28, 28, 1))
        
        regularization = tf.keras.regularizers.L1L2(l2=1e-5)

        t3 = self.block(input_img, 128, 0.2, regularization)
        t3 = self.block(t3, 256, 0.3, regularization)
        t3 = self.block(t3, 512, 0.4, regularization, False)

        conv = Conv2D(1024, (3,3), padding='valid', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(t3)
        net = BatchNormalization()(conv)
        conv = Conv2D(1024, (3,3), padding='valid', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(net)
        net = BatchNormalization()(conv)
        net = AveragePooling2D(pool_size=(2,2))(net)
        net = Flatten()(net)
        net = Dropout(0.2)(net)

        net = Dense(10, activation = 'softmax', kernel_regularizer=regularization, bias_regularizer=regularization)(net)

        bitmap = UpSampling2D(size=(4,4))(t3)
        bitmap = Conv2D(128, (3,3), padding='same', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(bitmap)
        bitmap = BatchNormalization()(bitmap)
        bitmap = Dropout(0.2)(bitmap)
        bitmap = Conv2D(256, (3,3), padding='same', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(bitmap)
        bitmap = BatchNormalization()(bitmap)
        bitmap = Dropout(0.2)(bitmap)
        bitmap = Conv2D(512, (3,3), padding='same', activation='relu', kernel_regularizer=regularization, bias_regularizer=regularization)(bitmap)
        bitmap = BatchNormalization()(bitmap)
        bitmap = Dropout(0.2)(bitmap)
        bitmap = Conv2D(1, (3,3), padding='same', activation='sigmoid', kernel_regularizer=regularization, bias_regularizer=regularization)(bitmap)

        super().__init__(inputs=input_img,outputs=[net,bitmap])
        
        schedule = tf.keras.optimizers.schedules.PolynomialDecay(
            initial_learning_rate=0.001,
            decay_steps=args.epochs*45000/500,
            end_learning_rate=0.0001
        )
        self.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=schedule),
            loss=[tf.keras.losses.CategoricalCrossentropy(from_logits=False, label_smoothing=0.1),tf.keras.losses.BinaryCrossentropy()],
            metrics=[tf.keras.metrics.CategoricalAccuracy(name="accuracy"),tf.keras.metrics.BinaryAccuracy(name="accuracy")])

        self.tb_callback=tf.keras.callbacks.TensorBoard(args.logdir, update_freq=1000, profile_batch=1)
        self.tb_callback.on_train_end = lambda *_: None

    def train(self, fashion_masks, args):
        t = fashion_masks.train.data["images"]
        d = fashion_masks.dev.data["images"]
        tr = tf.keras.utils.to_categorical(fashion_masks.train.data["labels"])
        de = tf.keras.utils.to_categorical(fashion_masks.dev.data["labels"])
        cb = tf.keras.callbacks.LambdaCallback(
            on_epoch_begin=lambda epoch, logs: print("Epoch {} begins".format(epoch)),
            on_epoch_end=lambda epoch, logs: self.save('model_{}.md5'.format(epoch))
        )
        self.fit(
            t, [tr, fashion_masks.train.data['masks']],
            batch_size=args.batch_size, epochs=args.epochs,
            validation_data=(d, [de, fashion_masks.dev.data['masks']]),
            callbacks=[self.tb_callback,cb],
        )

def standardize(image):
    m = np.mean(image)
    stddev = max([np.std(image), 1 / (28*28)])
    return (image - m) / stddev

def standardize_images(images):
    for i in range(len(images)):
        images[i] = standardize(images[i])
    return images

if __name__ == "__main__":
    import argparse
    import datetime
    import os
    import re

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch_size", default=32, type=int, help="Batch size.")
    parser.add_argument("--epochs", default=100, type=int, help="Number of epochs.")
    parser.add_argument("--threads", default=8, type=int, help="Maximum number of threads to use.")
    args = parser.parse_args()

    # Fix random seeds
    np.random.seed(42)
    tf.random.set_seed(42)
    tf.config.threading.set_inter_op_parallelism_threads(args.threads)
    tf.config.threading.set_intra_op_parallelism_threads(args.threads)

    # Create logdir name
    args.logdir = os.path.join("logs", "{}-{}-{}".format(
        os.path.basename(__file__),
        datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"),
        ",".join(("{}={}".format(re.sub("(.)[^_]*_?", r"\1", key), value) for key, value in sorted(vars(args).items())))
    ))

    # Load data
    fashion_masks = FashionMasks()
    fashion_masks.dev.data["images"] = standardize_images(fashion_masks.dev.data["images"])
    fashion_masks.test.data["images"] = standardize_images(fashion_masks.test.data["images"])
    fashion_masks.train.data["images"] = standardize_images(fashion_masks.train.data["images"])

    for i in range(len(fashion_masks.train.data['images'])):
        x0 = np.random.randint(0,high=28)
        y0 = np.random.randint(0,high=28)
        for x in range(-7,7):
            for y in range(-7,7):
                if x0 + x < 28 and y0 + y < 28 and x0 + x > 0 and y0 + y > 0:
                    fashion_masks.train.data["images"][i][x0 + x][y0 + y] = 0

    # Create the network and train
    network = Network(args)

    network.train(fashion_masks, args)
    #network.save('model.md5')
    #network.load_weights('model.md5')



    # Predict test data in args.logdir
    with open("fashion_masks_test.txt", "w", encoding="utf-8") as out_file:
        # TODO: Predict labels and masks on fashion_masks.test.data["images"],
        # into test_labels and test_masks (test_masks is assumed to be
        # a Numpy array with values 0/1).
            l, m = network.predict(fashion_masks.dev.data['images'], batch_size=32)
            
            for label, mask in zip(l, m):
                lab = np.argmax(label)
                ms = np.array(list(map(lambda x: x>=0.5, mask)))
                print(lab, *ms.astype(np.uint8).flatten(), file=out_file)
