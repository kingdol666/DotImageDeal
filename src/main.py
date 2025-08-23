from PIL import Image, ImageDraw
import numpy as np
from scipy.ndimage import gaussian_filter, label

def mark_dark_particles_adaptive(image_input, sensitivity=0.2, output_path='output/marked_result.png', blur_radius=15, border_width=10, selection_box=None, min_particle_size=0, max_particle_size=None):
    """
    使用局部自适应阈值和大小筛选，精准识别并标记深色粒子。
    能够适应光照不均，并过滤掉不符合尺寸要求的粒子。

    :param image_input: 输入图片路径或Pillow Image对象
    :param sensitivity: 识别灵敏度 (0.0 ~ 1.0)。
                        数值越高，识别标准越宽松，标记的粒子越多。
                        建议从 0.1 (最不灵敏) 到 0.9 (非常灵敏) 之间尝试。
    :param output_path: 标记后的图片保存路径
    :param blur_radius: 用于计算局部背景亮度的模糊半径。
                        该值应大于要识别的最大粒子的半径。
    :param border_width: 要忽略的边框宽度（像素）。此区域内的任何内容都不会被标记。
    :param selection_box: 一个元组 (left, top, right, bottom) 定义了要处理的区域。
                          如果为 None，则处理整个图像。
    :param min_particle_size: 标记的最小粒子面积（像素数）。
    :param max_particle_size: 标记的最大粒子面积（像素数）。如果为 None，则没有上限。
    """
    # 验证参数范围
    if not 0.0 <= sensitivity <= 1.0:
        raise ValueError("灵敏度(sensitivity)必须在 0.0 到 1.0 之间")

    # 根据输入类型加载图片
    if isinstance(image_input, str):
        img = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise TypeError("image_input 必须是文件路径 (str) 或 Pillow Image 对象")

    # 如果图像有alpha通道，则将其与白色背景混合
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert('RGB')

    # 如果定义了选框，则裁剪图像
    if selection_box:
        img_to_process = img.crop(selection_box)
    else:
        img_to_process = img

    img_array = np.array(img_to_process)
    gray_array = np.array(img_to_process.convert('L'))

    # 使用高斯模糊创建背景亮度图
    background_luminance = gaussian_filter(gray_array.astype(float), sigma=blur_radius)

    # 计算阈值
    threshold_factor = 0.5 + (sensitivity * 0.5)
    threshold = background_luminance * threshold_factor
    
    # 创建初始掩码
    initial_mask = gray_array < threshold

    # 过滤粒子大小
    if min_particle_size > 0 or max_particle_size is not None:
        # 识别独立的粒子区域
        labeled_array, num_features = label(initial_mask)
        
        # 计算每个粒子的大小
        particle_sizes = np.bincount(labeled_array.ravel())
        
        # 创建一个大小筛选掩码
        # 我们想要移除那些太小或太大的粒子
        # 首先，创建一个布尔数组，其中 particle_sizes 中符合条件的索引为 True
        size_mask = np.ones_like(particle_sizes, dtype=bool)
        size_mask[0] = False # 忽略背景
        if min_particle_size > 0:
            size_mask[particle_sizes < min_particle_size] = False
        if max_particle_size is not None:
            size_mask[particle_sizes > max_particle_size] = False
            
        # 从 labeled_array 中移除不符合条件的粒子
        # 获取所有不符合条件的粒子标签
        remove_labels = np.where(~size_mask)[0]
        
        # 创建最终掩码，只保留符合条件的粒子
        # np.isin 检查 labeled_array 中的每个元素是否存在于 remove_labels 中
        # 我们对结果取反，以保留 *不* 在 remove_labels 中的粒子
        final_mask = ~np.isin(labeled_array, remove_labels)
        mask = final_mask
    else:
        mask = initial_mask

    # 在处理区域内忽略边框
    if border_width > 0:
        mask[:border_width, :] = False
        mask[-border_width:, :] = False
        mask[:, :border_width] = False
        mask[:, -border_width:] = False

    # 创建结果图像，将掩码区域标记为红色
    result_array = img_array.copy()
    result_array[mask] = [255, 0, 0]

    # 将处理后的区域粘贴回原始图像（如果使用了选框）
    if selection_box:
        processed_part = Image.fromarray(result_array)
        img.paste(processed_part, selection_box)
        result_img = img
    else:
        result_img = Image.fromarray(result_array)

    # 在最终图像上绘制选框（如果提供）
    draw = ImageDraw.Draw(result_img)
    if selection_box:
        draw.rectangle(selection_box, outline="blue", width=2)

    # 计算百分比
    particle_area = np.sum(mask)
    total_area = mask.size
    percentage = (particle_area / total_area) * 100 if total_area > 0 else 0

    # 在图片上用蓝色笔迹刻印粒子所占面积
    text = f"Particle Area: {percentage:.2f}%"
    # 简单的定位逻辑：如果选框存在，则放在选框内，否则放在左上角
    if selection_box:
        text_position = (selection_box[0] + 5, selection_box[1] + 5)
    else:
        text_position = (15, 15)
    text_color = (0, 0, 255)  # 蓝色
    draw.text(text_position, text, fill=text_color)

    # 保存结果
    result_img.save(output_path)
    print(f"处理完成，结果已保存至 {output_path}")
    print(f"参数: 灵敏度={sensitivity}, 模糊半径={blur_radius}, 边框宽度={border_width}")
    print(f"深色粒子覆盖面积: {percentage:.2f}%")
    return result_img, percentage

# --- 示例调用 ---
if __name__ == '__main__':
    try:
        _, _ = mark_dark_particles_adaptive(
            image_input='images/12.png',
            sensitivity=0.2,
            output_path='output/marked_adaptive_corrected.png',
            blur_radius=10,
            border_width=20
        )
    except FileNotFoundError:
        print("错误：找不到图片文件。请确保 'images/12.png' 路径正确。")
    except Exception as e:
        print(f"发生错误: {e}")
