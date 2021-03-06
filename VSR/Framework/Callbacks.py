"""
Copyright: Intel Corp. 2018
Author: Wenyi Tang
Email: wenyi.tang@intel.com
Created Date: May 17th 2018
Updated Date: May 17th 2018

Training environment callbacks preset
"""

from pathlib import Path
from functools import partial
import numpy as np
from PIL.Image import Image

from ..Util.ImageProcess import array_to_img, img_to_array, bicubic_rescale


def _sub_residual(**kwargs):
    img = kwargs.get('input')
    res = kwargs.get('output') or np.zeros_like(img)
    res = res[0] if isinstance(res, list) else res
    return img - res


def _save_model_predicted_images(output, index, **kwargs):
    save_dir = kwargs.get('save_dir') or '.'
    name = kwargs.get('name')
    if output is not None:
        img = output[index] if isinstance(output, list) else output
        img = _to_normalized_image(img)
        path = Path(f'{save_dir}/{name}_PR.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        img.convert('RGB').save(str(path))
    return output


def _colored_grayscale_image(outputs, input, **kwargs):
    ret = []
    for img in outputs:
        assert img.shape[-1] == 1
        scale = np.array(img.shape[1:3]) // np.array(input.shape[1:3])
        uv = array_to_img(input[0], 'YCbCr')
        uv = bicubic_rescale(uv, scale)
        uv = img_to_array(uv)[..., 1:]
        img = np.concatenate([img[0], uv], axis=-1)
        img = np.clip(img, 0, 255)
        ret.append(array_to_img(img, 'YCbCr'))
    return ret


def _to_normalized_image(img):
    img = np.asarray(img)
    # squeeze to [H, W, C]
    for i in range(np.ndim(img)):
        try:
            img = np.squeeze(img, i)
        except ValueError:
            pass
    if img.dtype == np.float32 and img.max() <= 1.0:
        img = img * 255.0
    img = np.clip(img, 0, 255)
    if img.ndim == 2:
        return array_to_img(img, 'L')
    elif img.ndim == 3:
        return array_to_img(img, 'YCbCr')
    else:
        raise ValueError('Invalid img data, must be an array of 2D image1 with channel less than 3')


def _add_noise(feature, stddev, mean, clip, **kwargs):
    x = feature.astype('float') + np.random.normal(mean, stddev, feature.shape)
    return np.clip(x, 0, 255) if clip else x


def _add_random_noise(feature, low, high, step, mean, clip, **kwargs):
    n = list(range(low, high, step))
    i = np.random.randint(len(n))
    stddev = n[i]
    return _add_noise(feature, stddev, mean, clip)


def _gaussian_blur(feature, width, size, **kwargs):
    from scipy.ndimage.filters import gaussian_filter as gf

    y = []
    for img in np.split(feature, feature.shape[0]):
        c = []
        for channel in np.split(img, img.shape[-1]):
            channel = np.squeeze(channel).astype('float')
            c.append(gf(channel, width, mode='constant', truncate=(size // 2) / width))
        y.append(np.stack(c, axis=-1))
    return np.stack(y)


def _exponential_decay(lr, start_lr, epochs, steps, decay_step, decay_rate):
    return start_lr * decay_rate ** (steps / decay_step)


def _poly_decay(lr, start_lr, end_lr, epochs, steps, decay_step, power):
    return (start_lr - end_lr) * (1 - steps / decay_step) ** power + end_lr


def _stair_decay(lr, start_lr, epochs, steps, decay_step, decay_rate):
    return start_lr * decay_rate ** (steps // decay_step)


def _eval_psnr(output, label, **kwargs):
    if isinstance(output, Image):
        output = img_to_array(output.convert('RGB'))
    if isinstance(label, Image):
        label = img_to_array(label.convert('RGB'))
    if label.ndim == 4:
        label = label[0]
    assert output.shape == label.shape

    mse = np.mean(np.square(output - label))
    psnr = 20 * np.log10(255 / np.sqrt(mse))
    print(f'PSNR = {psnr:.2f}dB')


def save_image(save_dir='.', output_index=0):
    return partial(_save_model_predicted_images, save_dir=save_dir, index=output_index)


def print_psnr():
    return _eval_psnr


def reduce_residual(**kwargs):
    return partial(_sub_residual, **kwargs)


def to_rgb(**kwargs):
    return partial(_colored_grayscale_image, **kwargs)


def to_gray():
    def _gray_colored_image(inputs, **kwargs):
        return inputs[..., 0:1]

    return _gray_colored_image


def to_uv():
    def _uv_colored_image(inputs, **kwargs):
        return inputs[..., 1:]

    return _uv_colored_image


def add_noise(sigma, mean=0, clip=False):
    return partial(_add_noise, stddev=sigma, mean=mean, clip=clip)


def add_random_noise(low, high, step=1, mean=0, clip=False):
    return partial(_add_random_noise, low=low, high=high, step=step, mean=mean, clip=clip)


def lr_decay(method, lr, **kwargs):
    if method == 'exp':
        return partial(_exponential_decay, start_lr=lr, **kwargs)
    elif method == 'poly':
        return partial(_poly_decay, start_lr=lr, **kwargs)
    elif method == 'stair':
        return partial(_stair_decay, start_lr=lr, **kwargs)
    else:
        raise ValueError('invalid decay method!')


def blur(kernel_width, kernel_size, method='gaussian'):
    return partial(_gaussian_blur, width=kernel_width, size=kernel_size)
