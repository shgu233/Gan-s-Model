# -*- coding: utf-8 -*-


import time
import os
import numpy as np
import torch
import random

import torch.nn.functional as F
import torch.nn as nn
import torchvision.utils as vutils

from PIL import Image
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from torchvision import transforms


if torch.cuda.is_available():
    torch.backends.cudnn.deterministic = True

# Commented out IPython magic to ensure Python compatibility.
!pip install matplotlib

import matplotlib.pyplot as plt
# %matplotlib inline

from google.colab import drive
drive.mount("/content/drive/")

##########################
### SETTINGS
##########################

# Device

CUDA = 'cuda:2'
DEVICE = torch.device(CUDA if torch.cuda.is_available() else "cpu")

# Hyperparameters
RANDOM_SEED = 42
GENERATOR_LEARNING_RATE = 0.0002
DISCRIMINATOR_LEARNING_RATE = 0.0002
NUM_EPOCHS = 200
BATCH_SIZE = 128
NUM_WORKERS = 4 # workers for data loader

IMAGE_SIZE = (64, 64, 3)

# Size of the latent vector
LATENT_DIM = 100

# Number of feature maps in generator and discriminator
NUM_MAPS_GEN = 64
NUM_MAPS_DIS = 64

# Set random seeds for reproducibility
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED);

import os

drive_dir = '/content/drive/MyDrive'  # Change this to the root directory of your Google Drive

# List all files and directories in the drive_dir
file_list = os.listdir(drive_dir)
print(file_list)

import os

# Update file paths
train_cat_dir = '/content/drive/MyDrive/train/cat'

# Count the number of training cats
num_train_cats = len([i for i in os.listdir(train_cat_dir)
                      if i.endswith('.jpg') and i.startswith('cat')])

print(f'Training set cats: {num_train_cats}')

import random

class CatsDogsDataset(Dataset):
    """Custom Dataset for loading CelebA face images"""

    def __init__(self, img_dir, transform=None):

        self.img_dir = img_dir

        self.img_names = [i for i in
                          os.listdir(img_dir)
                          if i.endswith('.jpg')]

        self.y = []
        for i in self.img_names:
            if i.split('.')[0] == 'cat':
                self.y.append(0)
            else:
                self.y.append(1)

        self.transform = transform

    def __getitem__(self, index):
        img = Image.open(os.path.join(self.img_dir,
                                      self.img_names[index]))

        if self.transform is not None:
            img = self.transform(img)

        label = self.y[index]
        return img, label

    def __len__(self):
        return len(self.y)

data_transforms = {
    'train': transforms.Compose([
        #transforms.RandomRotation(5),
        #transforms.RandomHorizontalFlip(),
        transforms.RandomResizedCrop(IMAGE_SIZE[0], scale=(0.96, 1.0), ratio=(0.95, 1.05)),
        transforms.ToTensor(),
        # normalize images to [-1, 1] range
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ]),
    'valid': transforms.Compose([
        transforms.Resize([IMAGE_SIZE[0], IMAGE_SIZE[1]]),
        transforms.ToTensor(),
        # normalize images to [-1, 1] range
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ]),
}


train_dataset = CatsDogsDataset(img_dir=os.path.join('/content/drive/MyDrive/train/cat'),
                                transform=data_transforms['train'])

train_loader = DataLoader(dataset=train_dataset,
                          batch_size=BATCH_SIZE,
                          drop_last=True,
                          num_workers=NUM_WORKERS,
                          shuffle=True)

real_batch = next(iter(train_loader))
plt.figure(figsize=(8, 8))
plt.axis("off")
plt.title("Training Images")
plt.imshow(np.transpose(vutils.make_grid(real_batch[0][:64],
                                         padding=2, normalize=True),
                        (1, 2, 0)))

def weights_init(module):
    """
    Function that initializes weights according to
    Radford et al.'s DCGAN paper
    """
    classname = module.__class__.__name__
    if classname.find('Conv') != -1:
        nn.init.normal_(module.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        nn.init.normal_(module.weight.data, 1.0, 0.02)
        nn.init.constant_(module.bias.data, 0)

##########################
### MODEL
##########################

class DCGAN(torch.nn.Module):

    def __init__(self):
        super(DCGAN, self).__init__()


        self.generator = nn.Sequential(
            #
            # input size: vector z of size LATENT_DIM
            #
            nn.ConvTranspose2d(LATENT_DIM, NUM_MAPS_GEN*8,
                               kernel_size=4, stride=1, padding=0,
                               bias=False), # bias is redundant when using BatchNorm
            nn.BatchNorm2d(NUM_MAPS_GEN*8),
            nn.ReLU(True),
            #
            # size: NUM_MAPS_GEN*8 x 4 x 4
            #
            nn.ConvTranspose2d(NUM_MAPS_GEN*8, NUM_MAPS_GEN*4,
                               kernel_size=4, stride=2, padding=1,
                               bias=False),
            nn.BatchNorm2d(NUM_MAPS_GEN*4),
            nn.ReLU(True),
            #
            # size: NUM_MAPS_GEN*4 x 8 x 8
            #
            nn.ConvTranspose2d(NUM_MAPS_GEN*4, NUM_MAPS_GEN*2,
                               kernel_size=4, stride=2, padding=1,
                               bias=False),
            nn.BatchNorm2d(NUM_MAPS_GEN*2),
            nn.ReLU(True),
            #
            # size: NUM_MAPS_GEN*2 x 16 x 16
            #
            nn.ConvTranspose2d(NUM_MAPS_GEN*2, NUM_MAPS_GEN,
                               kernel_size=4, stride=2, padding=1,
                               bias=False),
            nn.BatchNorm2d(NUM_MAPS_GEN),
            nn.ReLU(True),
            #
            # size: NUM_MAPS_GEN x 32 x 32
            #
            nn.ConvTranspose2d(NUM_MAPS_GEN, IMAGE_SIZE[2],
                               kernel_size=4, stride=2, padding=1,
                               bias=False),
            #
            # size: IMAGE_SIZE[2] x 64 x 64
            #
            nn.Tanh()
        )

        self.discriminator = nn.Sequential(
            #
            # input size IMAGE_SIZE[2] x IMAGE_SIZE[0] x IMAGE_SIZE[1]
            #
            nn.Conv2d(IMAGE_SIZE[2], NUM_MAPS_DIS,
                      kernel_size=4, stride=2, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            #
            # size: NUM_MAPS_DIS x 32 x 32
            #
            nn.Conv2d(NUM_MAPS_DIS, NUM_MAPS_DIS*2,
                      kernel_size=4, stride=2, padding=1,
                      bias=False),
            nn.BatchNorm2d(NUM_MAPS_DIS*2),
            nn.LeakyReLU(0.2, inplace=True),
            #
            # size: NUM_MAPS_DIS*2 x 16 x 16
            #
            nn.Conv2d(NUM_MAPS_DIS*2, NUM_MAPS_DIS*4,
                      kernel_size=4, stride=2, padding=1,
                      bias=False),
            nn.BatchNorm2d(NUM_MAPS_DIS*4),
            nn.LeakyReLU(0.2, inplace=True),
            #
            # size: NUM_MAPS_DIS*4 x 8 x 8
            #
            nn.Conv2d(NUM_MAPS_DIS*4, NUM_MAPS_DIS*8,
                      kernel_size=4, stride=2, padding=1,
                      bias=False),
            nn.BatchNorm2d(NUM_MAPS_DIS*8),
            nn.LeakyReLU(0.2, inplace=True),
            #
            # size: NUM_MAPS_DIS*8 x 4 x 4
            #
            nn.Conv2d(NUM_MAPS_DIS*8, 1,
                      kernel_size=4, stride=1, padding=0),
            nn.Sigmoid()
        )


    def generator_forward(self, z):
        img = self.generator(z)
        return img

    def discriminator_forward(self, img):
        pred = model.discriminator(img)
        return pred

import torch.nn as nn

torch.manual_seed(RANDOM_SEED)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

loss_function = nn.BCELoss()

real_label = 1
fake_label = 0

# Batch of latent (noise) vectors for
# evaluating / visualizing the training progress
# of the generator
fixed_noise = torch.randn(64, LATENT_DIM, 1, 1, device=device)

model = DCGAN()
model = model.to(device)
model.apply(weights_init)

print(model)

if torch.cuda.is_available():
    torch.device('cuda')
else:
    torch.device('cpu')
    print("CPU")

!pip install torchsummary
from torchsummary import summary

# torchsummary can only use default cuda device, which
# causes issues if e.g., cuda:1 is used
CUDA_VISIBLE_DEVICES=1

# with torch.cuda.device(int(CUDA.split(':')[-1])):
summary(model.generator, input_size=(100, 1, 1), device='cuda')
summary(model.discriminator, input_size=((IMAGE_SIZE[2], IMAGE_SIZE[0], IMAGE_SIZE[1])), device='cuda')

optim_gener = torch.optim.Adam(model.generator.parameters(),
                               betas=(0.5, 0.999),
                               lr=GENERATOR_LEARNING_RATE)
optim_discr = torch.optim.Adam(model.discriminator.parameters(),
                               betas=(0.5, 0.999),
                               lr=DISCRIMINATOR_LEARNING_RATE)

# Commented out IPython magic to ensure Python compatibility.
start_time = time.time()

discr_costs = []
gener_costs = []
images_from_noise = []


for epoch in range(NUM_EPOCHS):
    model = model.train()
    for batch_idx, (features, targets) in enumerate(train_loader):


        # --------------------------
        # Train Discriminator
        # --------------------------

        optim_discr.zero_grad()

        real_images = features.to(device)
        num_real = real_images.size(0)
        real_label_vec = torch.full((num_real,), real_label, device=device)

        # get discriminator loss on real images
        discr_pred_real = model.discriminator_forward(real_images).view(-1)
#         real_label_vec = real_label_vec.to(torch.float32)
        discr_pred_real = discr_pred_real.to(torch.float32)
        real_label_vec = real_label_vec.to(torch.float32)
#         print(discr_pred_real.dtype, real_label_vec.dtype)
        real_loss = loss_function(discr_pred_real, real_label_vec)
        #real_loss.backward()

        # get discriminator loss on fake images
        random_vec = torch.randn(BATCH_SIZE, LATENT_DIM, 1, 1, device=device)
        fake_images = model.generator_forward(random_vec)
        fake_label_vec = torch.full((num_real,), fake_label, device=device)
        discr_pred_fake = model.discriminator_forward(fake_images.detach()).view(-1)
        fake_label_vec = fake_label_vec.to(torch.float32)
#         print(discr_pred_fake.dtype, fake_label_vec.dtype)
        fake_loss = loss_function(discr_pred_fake, fake_label_vec)
        #fake_loss.backward()

        # combined loss
        discr_loss = 0.5*(real_loss + fake_loss)
        discr_loss.backward()

        optim_discr.step()

        # --------------------------
        # Train Generator
        # --------------------------

        optim_gener.zero_grad()

        discr_pred_fake = model.discriminator_forward(fake_images).view(-1)
        gener_loss = loss_function(discr_pred_fake, real_label_vec)
        gener_loss.backward()

        optim_gener.step()

        # --------------------------
        # Logging
        # --------------------------
        discr_costs.append(discr_loss.item())
        gener_costs.append(gener_loss.item())


        ### LOGGING
        if not batch_idx % 100:
            print ('Epoch: %03d/%03d | Batch %03d/%03d | Gen/Dis Loss: %.4f/%.4f'
#                    %(epoch+1, NUM_EPOCHS, batch_idx,
                     len(train_loader), gener_loss, discr_loss))

    ### Save images for evaluation
    with torch.no_grad():
        fake_images = model.generator_forward(fixed_noise).detach().cpu()
        images_from_noise.append(
            vutils.make_grid(fake_images, padding=2, normalize=True))

    print('Time elapsed: %.2f min' % ((time.time() - start_time)/60))

print('Total Training Time: %.2f min' % ((time.time() - start_time)/60))

ax1 = plt.subplot(1, 1, 1)
ax1.plot(range(len(gener_costs)), gener_costs, label='Generator loss')
ax1.plot(range(len(discr_costs)), discr_costs, label='Discriminator loss')
ax1.set_xlabel('Iterations')
ax1.set_ylabel('Loss')
ax1.legend()
# Set scond x-axis  `
ax2 = ax1.twiny()
newlabel = list(range(NUM_EPOCHS+1))
iter_per_epoch = len(train_loader)
newpos = [e*iter_per_epoch for e in newlabel]

ax2.set_xticklabels(newlabel[::10])
ax2.set_xticks(newpos[::10])

ax2.xaxis.set_ticks_position('bottom')
ax2.xaxis.set_label_position('bottom')
ax2.spines['bottom'].set_position(('outward', 45))
ax2.set_xlabel('Epochs')
ax2.set_xlim(ax1.get_xlim())
###################

plt.show()

##########################
### VISUALIZATION
##########################

for i in range(0, NUM_EPOCHS, 5):
    plt.imshow(np.transpose(images_from_noise[i], (1, 2, 0)))
    plt.show()

##########################
### VISUALIZATION
##########################

for i in range(0, NUM_EPOCHS, 5):
    plt.imshow(np.transpose(images_from_noise[i], (1, 2, 0)))
    plt.show()

plt.figure(figsize=(10, 10))
plt.imshow(np.transpose(images_from_noise[-1], (1, 2, 0)))
plt.show()

