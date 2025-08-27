from PIL import Image, ImageDraw
import numpy as np
from scipy.ndimage import gaussian_filter, label, center_of_mass
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt

def mark_dark_particles_adaptive(image_input, sensitivity_min=0.2, sensitivity_max=0.9, output_path='output/marked_result.png', blur_radius=15, border_width=10, selection_box=None, min_particle_size=0, max_particle_size=None):
    """
    使用局部自适应阈值和大小筛选，精准识别并标记在特定灵敏度范围内的深色粒子。
    能够适应光照不均，并过滤掉不符合尺寸要求的粒子。

    :param image_input: 输入图片路径或Pillow Image对象
    :param sensitivity_min: 识别灵敏度下限 (0.0 ~ 1.0)。
    :param sensitivity_max: 识别灵敏度上限 (0.0 ~ 1.0)。
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
    if not (0.0 <= sensitivity_min <= 1.0 and 0.0 <= sensitivity_max <= 1.0):
        raise ValueError("灵敏度(sensitivity)必须在 0.0 到 1.0 之间")
    if sensitivity_min > sensitivity_max:
        sensitivity_min, sensitivity_max = sensitivity_max, sensitivity_min # 自动交换

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

    # 计算阈值范围
    # 灵敏度越高，阈值越高，更容易将像素识别为粒子
    threshold_factor_max = 0.5 + (sensitivity_max * 0.5)
    threshold_high = background_luminance * threshold_factor_max

    threshold_factor_min = 0.5 + (sensitivity_min * 0.5)
    threshold_low = background_luminance * threshold_factor_min
    
    # 创建初始掩码，选择在两个阈值之间的像素
    # 即，比最宽松的标准暗，但又比最严格的标准亮
    mask_below_high_threshold = gray_array < threshold_high
    mask_above_low_threshold = gray_array >= threshold_low
    initial_mask = mask_below_high_threshold & mask_above_low_threshold
    num_particles = 0

    # 过滤粒子大小
    if min_particle_size > 0 or max_particle_size is not None:
        # 识别独立的粒子区域
        labeled_array, num_features = label(initial_mask)
        
        # 计算每个粒子的大小
        particle_sizes = np.bincount(labeled_array.ravel())
        
        # 创建一个大小筛选掩码
        size_mask = np.ones_like(particle_sizes, dtype=bool)
        size_mask[0] = False # 忽略背景
        if min_particle_size > 0:
            size_mask[particle_sizes < min_particle_size] = False
        if max_particle_size is not None:
            size_mask[particle_sizes > max_particle_size] = False
            
        # 计算符合条件的粒子数量
        num_particles = np.sum(size_mask)
        
        # 从 labeled_array 中移除不符合条件的粒子
        remove_labels = np.where(~size_mask)[0]
        
        # 创建最终掩码
        final_mask = ~np.isin(labeled_array, remove_labels)
        mask = final_mask
    else:
        mask = initial_mask
        # 如果不过滤大小，也计算粒子总数
        _, num_particles = label(mask)

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

    # 在图片上用蓝色笔迹刻印粒子信息
    text_percentage = f"Particle Area: {percentage:.2f}%"
    text_count = f"Particle Count: {num_particles}"
    
    # 简单的定位逻辑
    if selection_box:
        text_pos1 = (selection_box[0] + 5, selection_box[1] + 5)
        text_pos2 = (selection_box[0] + 5, selection_box[1] + 20)
    else:
        text_pos1 = (15, 15)
        text_pos2 = (15, 30)
        
    text_color = (0, 0, 255)  # 蓝色
    draw.text(text_pos1, text_percentage, fill=text_color)
    draw.text(text_pos2, text_count, fill=text_color)

    # 保存结果
    result_img.save(output_path)
    print(f"处理完成，结果已保存至 {output_path}")
    print(f"参数: 灵敏度范围=[{sensitivity_min:.2f}, {sensitivity_max:.2f}], 模糊半径={blur_radius}, 边框宽度={border_width}")
    print(f"深色粒子覆盖面积: {percentage:.2f}%")
    print(f"检测到的粒子数量: {num_particles}")
    return result_img, percentage, num_particles


def mark_dark_particles_gradient(image_input, sensitivity_min=0.2, sensitivity_max=0.9, output_path='output/marked_gradient.png', blur_radius=15, border_width=10, selection_box=None, min_particle_size=0, max_particle_size=None):
    """
    改进版：使用局部自适应阈值和大小筛选，并根据粒子暗度应用不同深浅的红色标记。
    暗度越高的粒子，红色越深，实现平滑过渡效果。

    :param image_input: 输入图片路径或Pillow Image对象
    :param sensitivity_min: 识别灵敏度下限 (0.0 ~ 1.0)。
    :param sensitivity_max: 识别灵敏度上限 (0.0 ~ 1.0)。
    :param output_path: 标记后的图片保存路径
    :param blur_radius: 用于计算局部背景亮度的模糊半径。
    :param border_width: 要忽略的边框宽度（像素）。
    :param selection_box: 一个元组 (left, top, right, bottom) 定义处理区域。
    :param min_particle_size: 标记的最小粒子面积（像素数）。
    :param max_particle_size: 标记的最大粒子面积（像素数）。
    """
    if not (0.0 <= sensitivity_min <= 1.0 and 0.0 <= sensitivity_max <= 1.0):
        raise ValueError("灵敏度(sensitivity)必须在 0.0 到 1.0 之间")
    if sensitivity_min > sensitivity_max:
        sensitivity_min, sensitivity_max = sensitivity_max, sensitivity_min

    if isinstance(image_input, str):
        img = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise TypeError("image_input 必须是文件路径 (str) 或 Pillow Image 对象")

    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert('RGB')

    if selection_box:
        img_to_process = img.crop(selection_box)
    else:
        img_to_process = img

    img_array = np.array(img_to_process)
    gray_array = np.array(img_to_process.convert('L'))

    background_luminance = gaussian_filter(gray_array.astype(float), sigma=blur_radius)

    threshold_factor_max = 0.5 + (sensitivity_max * 0.5)
    threshold_high = background_luminance * threshold_factor_max

    threshold_factor_min = 0.5 + (sensitivity_min * 0.5)
    threshold_low = background_luminance * threshold_factor_min
    
    mask_below_high_threshold = gray_array < threshold_high
    mask_above_low_threshold = gray_array >= threshold_low
    initial_mask = mask_below_high_threshold & mask_above_low_threshold
    
    num_particles = 0
    if min_particle_size > 0 or max_particle_size is not None:
        labeled_array, num_features = label(initial_mask)
        particle_sizes = np.bincount(labeled_array.ravel())
        size_mask = np.ones_like(particle_sizes, dtype=bool)
        size_mask[0] = False
        if min_particle_size > 0:
            size_mask[particle_sizes < min_particle_size] = False
        if max_particle_size is not None:
            size_mask[particle_sizes > max_particle_size] = False
        num_particles = np.sum(size_mask)
        remove_labels = np.where(~size_mask)[0]
        final_mask = ~np.isin(labeled_array, remove_labels)
        mask = final_mask
    else:
        mask = initial_mask
        _, num_particles = label(mask)

    if border_width > 0:
        mask[:border_width, :] = False
        mask[-border_width:, :] = False
        mask[:, :border_width] = False
        mask[:, -border_width:] = False

    # --- 核心改进：颜色渐变 ---
    result_array = img_array.copy()
    
    # 获取掩码区域内的像素值和阈值
    masked_gray = gray_array[mask]
    masked_thresh_low = threshold_low[mask]
    masked_thresh_high = threshold_high[mask]

    # 计算暗度强度 (0.0 to 1.0)，避免除以零
    denominator = masked_thresh_high - masked_thresh_low
    # np.clip(denominator, a_min=1e-5, a_max=None, out=denominator)
    denominator[denominator < 1e-5] = 1e-5 # 避免除零
    
    intensity = (masked_thresh_high - masked_gray) / denominator
    intensity = np.clip(intensity, 0.0, 1.0) # 确保强度在[0,1]范围内

    # 将强度映射到红色通道 (例如, 从100到255)
    # 强度越高，红色越深
    red_channel = (100 + intensity * 155).astype(np.uint8)
    
    # 创建颜色数组
    gradient_colors = np.zeros((len(red_channel), 3), dtype=np.uint8)
    gradient_colors[:, 0] = red_channel # R通道
    
    # 应用渐变颜色
    result_array[mask] = gradient_colors
    # --- 改进结束 ---

    if selection_box:
        processed_part = Image.fromarray(result_array)
        img.paste(processed_part, selection_box)
        result_img = img
    else:
        result_img = Image.fromarray(result_array)

    draw = ImageDraw.Draw(result_img)
    if selection_box:
        draw.rectangle(selection_box, outline="blue", width=2)

    particle_area = np.sum(mask)
    total_area = mask.size
    percentage = (particle_area / total_area) * 100 if total_area > 0 else 0

    text_percentage = f"Particle Area: {percentage:.2f}%"
    text_count = f"Particle Count: {num_particles}"
    
    if selection_box:
        text_pos1 = (selection_box[0] + 5, selection_box[1] + 5)
        text_pos2 = (selection_box[0] + 5, selection_box[1] + 20)
    else:
        text_pos1 = (15, 15)
        text_pos2 = (15, 30)
        
    text_color = (0, 0, 255)
    draw.text(text_pos1, text_percentage, fill=text_color)
    draw.text(text_pos2, text_count, fill=text_color)

    result_img.save(output_path)
    print(f"处理完成，渐变结果已保存至 {output_path}")
    print(f"参数: 灵敏度范围=[{sensitivity_min:.2f}, {sensitivity_max:.2f}], 模糊半径={blur_radius}, 边框宽度={border_width}")
    print(f"深色粒子覆盖面积: {percentage:.2f}%")
    print(f"检测到的粒子数量: {num_particles}")
    return result_img, percentage, num_particles


def mark_particles_with_clustering(image_input, sensitivity_min=0.2, sensitivity_max=0.9, output_path='output/marked_clustered.png', blur_radius=15, border_width=10, selection_box=None, min_particle_size=0, max_particle_size=None, cluster_eps=50, cluster_min_samples=5):
    """
    在识别出的粒子基础上，使用DBSCAN聚类算法对粒子进行分组，并为每个簇分配独特的颜色。

    :param image_input: 输入图片路径或Pillow Image对象
    :param sensitivity_min: 识别灵敏度下限 (0.0 ~ 1.0)。
    :param sensitivity_max: 识别灵敏度上限 (0.0 ~ 1.0)。
    :param output_path: 标记后的图片保存路径
    :param blur_radius: 用于计算局部背景亮度的模糊半径。
    :param border_width: 要忽略的边框宽度（像素）。
    :param selection_box: 一个元组 (left, top, right, bottom) 定义处理区域。
    :param min_particle_size: 标记的最小粒子面积（像素数）。
    :param max_particle_size: 标记的最大粒子面积（像素数）。
    :param cluster_eps: DBSCAN聚类中两个样本被视为邻居的最大距离。
    :param cluster_min_samples: DBSCAN聚类中一个点被视为核心点的邻域中的样本数。
    """
    # --- 粒子识别部分 (与 adaptive 方法类似) ---
    if not (0.0 <= sensitivity_min <= 1.0 and 0.0 <= sensitivity_max <= 1.0):
        raise ValueError("灵敏度(sensitivity)必须在 0.0 到 1.0 之间")
    if sensitivity_min > sensitivity_max:
        sensitivity_min, sensitivity_max = sensitivity_max, sensitivity_min

    if isinstance(image_input, str):
        img = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise TypeError("image_input 必须是文件路径 (str) 或 Pillow Image 对象")

    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert('RGB')

    if selection_box:
        img_to_process = img.crop(selection_box)
    else:
        img_to_process = img

    img_array = np.array(img_to_process)
    gray_array = np.array(img_to_process.convert('L'))
    background_luminance = gaussian_filter(gray_array.astype(float), sigma=blur_radius)
    
    threshold_factor_max = 0.5 + (sensitivity_max * 0.5)
    threshold_high = background_luminance * threshold_factor_max
    threshold_factor_min = 0.5 + (sensitivity_min * 0.5)
    threshold_low = background_luminance * threshold_factor_min
    
    initial_mask = (gray_array < threshold_high) & (gray_array >= threshold_low)
    
    labeled_array, num_features = label(initial_mask)
    
    if min_particle_size > 0 or max_particle_size is not None:
        particle_sizes = np.bincount(labeled_array.ravel())
        size_mask = np.ones_like(particle_sizes, dtype=bool)
        size_mask[0] = False
        if min_particle_size > 0:
            size_mask[particle_sizes < min_particle_size] = False
        if max_particle_size is not None:
            size_mask[particle_sizes > max_particle_size] = False
        remove_labels = np.where(~size_mask)[0]
        final_mask = ~np.isin(labeled_array, remove_labels)
        labeled_array[~final_mask] = 0 # 更新labeled_array以移除不符合条件的粒子
    
    if border_width > 0:
        labeled_array[:border_width, :] = 0
        labeled_array[-border_width:, :] = 0
        labeled_array[:, :border_width] = 0
        labeled_array[:, -border_width:] = 0

    # --- 聚类和着色部分 ---
    particle_labels = np.unique(labeled_array)[1:] # 排除背景0
    if len(particle_labels) == 0:
        print("未检测到符合条件的粒子。")
        return img, 0, 0

    # 计算每个粒子的质心
    centroids = np.array(center_of_mass(initial_mask, labeled_array, particle_labels))
    
    # 应用DBSCAN聚类
    clustering = DBSCAN(eps=cluster_eps, min_samples=cluster_min_samples).fit(centroids)
    cluster_labels = clustering.labels_
    
    # 为每个簇生成一个独特的颜色
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    
    cluster_colors = {}
    if n_clusters > 0:
        # 使用新的API获取颜色映射来解决DeprecationWarning
        cmap = plt.colormaps.get_cmap('gist_rainbow')
        # 生成n_clusters个颜色
        colors_rgba = cmap(np.linspace(0, 1, n_clusters))
        
        for i in range(n_clusters):
            # 将 (r, g, b, a) 转换为 (r, g, b) 整数
            cluster_colors[i] = tuple(int(c * 255) for c in colors_rgba[i][:3])
    
    # 噪声点的颜色（例如灰色）
    noise_color = (128, 128, 128)

    # 创建结果图像
    result_array = img_array.copy()
    
    # 为每个粒子上色
    for particle_id, cluster_id in zip(particle_labels, cluster_labels):
        color = cluster_colors.get(cluster_id, noise_color)
        result_array[labeled_array == particle_id] = color

    # --- 后续处理 (与之前类似) ---
    if selection_box:
        processed_part = Image.fromarray(result_array)
        img.paste(processed_part, selection_box)
        result_img = img
    else:
        result_img = Image.fromarray(result_array)

    draw = ImageDraw.Draw(result_img)
    if selection_box:
        draw.rectangle(selection_box, outline="blue", width=2)

    final_mask = labeled_array > 0
    particle_area = np.sum(final_mask)
    total_area = final_mask.size
    percentage = (particle_area / total_area) * 100 if total_area > 0 else 0
    num_particles = len(particle_labels)
    num_clusters_found = n_clusters

    text_percentage = f"Particle Area: {percentage:.2f}%"
    text_count = f"Particle Count: {num_particles}"
    text_clusters = f"Cluster Count: {num_clusters_found}"
    
    if selection_box:
        text_pos1 = (selection_box[0] + 5, selection_box[1] + 5)
        text_pos2 = (selection_box[0] + 5, selection_box[1] + 20)
        text_pos3 = (selection_box[0] + 5, selection_box[1] + 35)
    else:
        text_pos1 = (15, 15)
        text_pos2 = (15, 30)
        text_pos3 = (15, 45)
        
    text_color = (0, 0, 255)
    draw.text(text_pos1, text_percentage, fill=text_color)
    draw.text(text_pos2, text_count, fill=text_color)
    draw.text(text_pos3, text_clusters, fill=text_color)

    result_img.save(output_path)
    print(f"聚类处理完成，结果已保存至 {output_path}")
    print(f"参数: 灵敏度=[{sensitivity_min:.2f}, {sensitivity_max:.2f}], 模糊半径={blur_radius}, 边框={border_width}")
    print(f"聚类参数: eps={cluster_eps}, min_samples={cluster_min_samples}")
    print(f"深色粒子覆盖面积: {percentage:.2f}%")
    print(f"检测到的粒子数量: {num_particles}")
    print(f"识别出的簇数量: {num_clusters_found}")
    return result_img, percentage, num_particles, num_clusters_found


# --- 示例调用 ---
if __name__ == '__main__':
    try:
        # 调用原始函数
        print("--- Running Original Adaptive Method ---")
        mark_dark_particles_adaptive(
            image_input='images/12.png',
            sensitivity_min=0.2,
            sensitivity_max=0.8,
            output_path='output/marked_adaptive_corrected.png',
            blur_radius=10,
            border_width=20
        )
        
        # 调用新的渐变函数
        print("\n--- Running New Gradient Method ---")
        mark_dark_particles_gradient(
            image_input='images/12.png',
            sensitivity_min=0.2,
            sensitivity_max=0.8,
            output_path='output/marked_gradient_corrected.png',
            blur_radius=10,
            border_width=20
        )

        # 调用新的聚类函数
        print("\n--- Running New Clustering Method ---")
        mark_particles_with_clustering(
            image_input='images/10.png',
            sensitivity_min=0.2,
            sensitivity_max=0.8,
            output_path='output/marked_clustered_corrected.png',
            blur_radius=10,
            border_width=20,
            min_particle_size=10, # 过滤掉非常小的噪声点
            cluster_eps=40,       # 簇内点的最大距离
            cluster_min_samples=3 # 一个簇最少需要3个粒子
        )
    except FileNotFoundError:
        print("错误：找不到图片文件。请确保 'images/12.png' 路径正确。")
    except Exception as e:
        print(f"发生错误: {e}")
        # 调用原始函数
        print("--- Running Original Adaptive Method ---")
        mark_dark_particles_adaptive(
            image_input='images/12.png',
            sensitivity_min=0.2,
            sensitivity_max=0.8,
            output_path='output/marked_adaptive_corrected.png',
            blur_radius=10,
            border_width=20
        )
        
        # 调用新的渐变函数
        print("\n--- Running New Gradient Method ---")
        mark_dark_particles_gradient(
            image_input='images/12.png',
            sensitivity_min=0.2,
            sensitivity_max=0.8,
            output_path='output/marked_gradient_corrected.png',
            blur_radius=10,
            border_width=20
        )
    except FileNotFoundError:
        print("错误：找不到图片文件。请确保 'images/12.png' 路径正确。")
    except Exception as e:
        print(f"发生错误: {e}")
