import os
import numpy as np
import torch
import cv2
import rasterio
from PIL import Image
from torch.utils.data import Dataset
from sklearn.model_selection import train_test_split


#cropping image
def random_crop(img, img_dim:tuple, upscaling_dim:tuple):
    i_width, i_height = img_dim
    u_width, u_height = upscaling_dim
    x=np.random.uniform(low=0,high=int(u_height-i_height))
    y=np.random.uniform(low=0,high=int(u_width-i_width))
    c_img=img[:, int(x):int(x)+i_height, int(y):int(y)+i_width]
    return c_img


#normalize data
def normalize_data(img, norm_range:tuple=(0,1)):
    assert norm_range==(0,1) or norm_range==(-1,1)
    if norm_range==(0,1):
        n_img=img/255
    else:
        n_img=(img/127.5)-1
    return n_img


#convert image to numpy array
def img2np(img_path, jpg=False):
    if jpg:
        array=cv2.cvtColor(np.array(Image.open(img_path)), cv2.COLOR_BGR2GRAY) 
    else:
        array=rasterio.open(img_path).read()[0] 
    return array


#augment data
def augment_data(input_imgs:list, 
                 target_img:np.array, 
                 img_dim:tuple, 
                 input_channel:int=3,
                 upscaling:int=100,
                 normalize:bool=False,
                 norm_range:tuple=(0,1)):
    #resizing
    u_factor=np.round((upscaling/100),1)
    u_img_dim=(int(img_dim[0]*u_factor), int(img_dim[1]*u_factor))
    target_img=cv2.resize(target_img, u_img_dim, interpolation=cv2.INTER_NEAREST)
    stacked_imgs=[cv2.resize(input_img, u_img_dim, interpolation=cv2.INTER_NEAREST) for input_img in input_imgs]
    stacked_imgs.append(target_img)
    stacked_imgs=np.stack(stacked_imgs, axis=0)
    #random jittering
    c_img=random_crop(stacked_imgs, img_dim, u_img_dim)
    j_input_imgs, j_target_img=c_img[0:input_channel], c_img[input_channel]
    #random mirroring
    random_factor=torch.rand(())
    if random_factor>0.5:
        m_input_imgs=np.array([np.fliplr(j_input_img) for j_input_img in j_input_imgs])
        m_target_img=np.fliplr(j_target_img)
    else:
        m_input_imgs=j_input_imgs
        m_target_img=j_target_img
    #normalize
    if normalize:
        n_input_imgs=normalize_data(m_input_imgs, norm_range)
        n_target_img=normalize_data(m_target_img, norm_range)
    else:
        n_input_imgs=m_input_imgs
        n_target_img=m_target_img
    return n_input_imgs, n_target_img


#load data
def load_dataset(input_img_src:list, 
                 target_img_src:str, 
                 partition:str='train', 
                 test_size:float=0.2, 
                 val_size:float=0.1,
                 seed=0,
                 img_format:str='tiff'):
    assert partition in ['train', 'val', 'test']
    #load image
    num_files=len(os.listdir(target_img_src))
    target_imgs=[img2np(f"{target_img_src}/{i}.{img_format}") 
                 for i in range(1, num_files+1)]
    input_imgs=[[img2np(f"{input_img_src[j]}/{i}.{img_format}") 
                 for i in range(1, num_files+1)] 
                for j in range(len(input_img_src))]
    #create train-val-test sets
    target_imgs_train_, target_imgs_test=train_test_split(target_imgs, 
                                                          test_size=np.round(test_size, 1), 
                                                          random_state=seed)
    
    target_imgs_train, target_imgs_val=train_test_split(target_imgs_train_, 
                                                        test_size=np.round(val_size, 1), 
                                                        random_state=seed)
        
    _input_imgs_train, input_imgs_train, input_imgs_val, input_imgs_test=[], [], [], []
    
    for k in range(len(input_img_src)):
        _k_input_imgs_train, k_input_imgs_test=train_test_split(input_imgs[k], 
                                                                test_size=np.round(test_size, 1), 
                                                                random_state=seed)
        _input_imgs_train.append(_k_input_imgs_train)
        input_imgs_test.append(k_input_imgs_test)
    
    for l in range(len(_input_imgs_train)):
        l_input_imgs_train, l_input_imgs_val=train_test_split(_input_imgs_train[l], 
                                                               test_size=np.round(val_size, 1), 
                                                               random_state=seed)
        input_imgs_train.append(l_input_imgs_train)
        input_imgs_val.append(l_input_imgs_val)
    #create train-val-test sets
    if partition=='train':
        return input_imgs_train, target_imgs_train
    elif partition=='val':
        return input_imgs_val, target_imgs_val
    else:
        return input_imgs_test, target_imgs_test


#define dataset class
class VPCHM(Dataset):
    def __init__(self, input_img_src:list, 
                 target_img_src:str, 
                 partition:str='train',
                 test_size:float=0.2, 
                 val_size:float=0.1, 
                 seed=0,
                 upscaling:int=100,
                 padding_dim:tuple=(1200,1200)):
        assert partition in ['train', 'val', 'test']
        self.input_imgs, self.target_imgs=load_dataset(input_img_src, 
                                                       target_img_src, 
                                                       partition, 
                                                       test_size, 
                                                       val_size, 
                                                       seed)
        self.partition=partition
        self.input_channel=len(input_img_src)
        self.upscaling=upscaling 
        self.padding_dim=padding_dim
    def __getitem__(self, item):
        input_imgs=[self.input_imgs[i][item] for i in range(self.input_channel)]
        target_img=self.target_imgs[item]
        img_dim=(target_img.shape[1], target_img.shape[0])
        if self.partition=='train':
            a_input_imgs, a_target_img=augment_data(input_imgs, target_img, img_dim, 
                                                    self.input_channel, self.upscaling)
            a_input_imgs=torch.Tensor(a_input_imgs)
            a_target_img=torch.Tensor(a_target_img) 
        else:
            a_input_imgs=torch.Tensor(input_imgs)
            a_target_img=torch.Tensor(target_img).unsqueeze(0)
        #padding
        p_input_imgs=torch.zeros(self.input_channel, self.padding_dim[0], self.padding_dim[1])
        p_input_imgs[:, :target_img.shape[0], :target_img.shape[1]]=a_input_imgs
        p_target_img=torch.zeros(1, self.padding_dim[0], self.padding_dim[1])
        p_target_img[:, :target_img.shape[0], :target_img.shape[1]]=a_target_img
        return p_input_imgs, p_target_img
    def __len__(self):
        return len(self.target_imgs)
