import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton,
                             QVBoxLayout, QWidget, QFileDialog, QHBoxLayout,
                             QSlider, QDoubleSpinBox, QFrame, QRubberBand,
                             QProgressDialog, QLineEdit, QGroupBox, QGridLayout, QSizePolicy, QMessageBox, QDialog, QScrollArea, QStyle, QSplitter)
from PyQt6.QtGui import QPixmap, QIcon, QFont, QFont
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal
from PIL import Image, ImageDraw
from PIL.ImageQt import ImageQt
from main import mark_dark_particles_adaptive

class ScaledPixmapLabel(QLabel):
    """
    一个自定义的QLabel，可以自动缩放其显示的QPixmap以适应窗口大小，同时保持原始的宽高比。
    """
    def __init__(self, *args, **kwargs):
        """
        构造函数。初始化QLabel并设置最小尺寸。
        """
        super().__init__(*args, **kwargs)
        self.setMinimumSize(1, 1)
        self._unscaled_pixmap = QPixmap()

    def setPixmap(self, pixmap):
        """
        设置要显示的原始QPixmap。

        Args:
            pixmap (QPixmap): 未经缩放的原始图像。
        """
        self._unscaled_pixmap = pixmap
        self._update_scaled_pixmap()

    def pixmap(self):
        """
        重写父类方法，返回当前正在显示的、已经过缩放的QPixmap。

        Returns:
            QPixmap: 已缩放的图像。
        """
        return super().pixmap()

    def unscaled_pixmap(self):
        """
        返回未经缩放的原始QPixmap。

        Returns:
            QPixmap: 原始图像。
        """
        return self._unscaled_pixmap

    def resizeEvent(self, event):
        """
        当窗口大小改变时触发的事件，调用更新缩放图像的方法。

        Args:
            event (QResizeEvent): 尺寸改变事件。
        """
        self._update_scaled_pixmap()
        super().resizeEvent(event)

    def _update_scaled_pixmap(self):
        """
        根据当前窗口的大小，重新计算并设置缩放后的QPixmap。
        """
        if self._unscaled_pixmap.isNull():
            super().setPixmap(QPixmap())
            return
        
        scaled = self._unscaled_pixmap.scaled(self.size(),
                                             Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
        super().setPixmap(scaled)

class ImageSelectionLabel(ScaledPixmapLabel):
    """
    继承自ScaledPixmapLabel，增加了使用鼠标进行矩形区域选择（橡皮筋）的功能。
    """
    selection_changed = pyqtSignal() # 当选区发生变化时发射的信号

    def __init__(self, *args, **kwargs):
        """
        构造函数。初始化父类和橡皮筋选择工具。
        """
        super().__init__(*args, **kwargs)
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.selection_origin = QPoint()

    def mousePressEvent(self, event):
        """
        当鼠标左键按下时，开始橡皮筋选择。

        Args:
            event (QMouseEvent): 鼠标事件。
        """
        if event.button() == Qt.MouseButton.LeftButton and not self.unscaled_pixmap().isNull():
            self.selection_origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.selection_origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        """
        当鼠标拖动时，更新橡皮筋选区的大小。

        Args:
            event (QMouseEvent): 鼠标事件。
        """
        if not self.selection_origin.isNull() and not self.unscaled_pixmap().isNull():
            self.rubber_band.setGeometry(QRect(self.selection_origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        """
        当鼠标左键释放时，结束选择并隐藏橡皮筋，同时发射selection_changed信号。

        Args:
            event (QMouseEvent): 鼠标事件。
        """
        if event.button() == Qt.MouseButton.LeftButton and not self.unscaled_pixmap().isNull():
            self.rubber_band.hide()
            self.selection_changed.emit()

    def get_selection(self):
        """
        获取当前橡皮筋选区的几何信息。

        Returns:
            QRect: 选区的矩形。
        """
        return self.rubber_band.geometry()

class MainWindow(QMainWindow):
    """
    程序的主窗口类，负责UI的初始化、布局和所有用户交互逻辑。
    """
    def __init__(self):
        """
        构造函数。初始化整个用户界面。
        """
        super().__init__()
        self.setWindowTitle("Dark Particle Analyzer - 深色粒子分析器")
        self.setGeometry(100, 100, 1600, 700)
        self.setWindowIcon(QIcon("public\images\icon.svg"))

        # 初始化图像显示区域
        self.original_image_label = ImageSelectionLabel()
        self.original_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.original_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.original_image_label.selection_changed.connect(self.process_image)

        self.processed_image_label = ScaledPixmapLabel("点击Load Image按钮选择一张需要处理的模板图像.")
        self.processed_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processed_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.processed_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 初始化功能按钮
        self.load_button = QPushButton("Load Image")
        self.load_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.load_button.clicked.connect(self.load_image)

        self.save_button = QPushButton("Save Result")
        self.save_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_button.clicked.connect(self.save_image)
        self.save_button.setEnabled(False)
        
        self.clear_button = QPushButton("Clear Selection")
        self.clear_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.clear_button.clicked.connect(self.clear_selection)
        self.clear_button.setEnabled(False)

        self.batch_button = QPushButton("Batch Process")
        self.batch_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        self.batch_button.clicked.connect(self.batch_process_images)

        self.theme_button = QPushButton("Toggle Theme")
        self.theme_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.theme_button.clicked.connect(self.toggle_theme)

        self.help_button = QPushButton("Help")
        self.help_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion))
        self.help_button.clicked.connect(self.show_help)

        # 为按钮设置对象名以便在QSS中应用特定样式
        self.load_button.setObjectName("iconButton")
        self.save_button.setObjectName("iconButton")
        self.clear_button.setObjectName("iconButton")
        self.batch_button.setObjectName("iconButton")
        self.theme_button.setObjectName("iconButton")
        self.help_button.setObjectName("iconButton")
        
        # --- 参数设置区域 ---
        params_group = QGroupBox("Processing Parameters")
        params_layout = QGridLayout(params_group)

        # 灵敏度下限
        self.sensitivity_min_label = QLabel("Sensitivity Min:")
        self.sensitivity_min_label.setToolTip("识别灵敏度下限 (0.0 ~ 1.0)。")
        self.sensitivity_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_min_slider.setRange(0, 100)
        self.sensitivity_min_slider.setValue(20)
        self.sensitivity_min_spinbox = QDoubleSpinBox()
        self.sensitivity_min_spinbox.setRange(0.0, 1.0)
        self.sensitivity_min_spinbox.setSingleStep(0.01)
        self.sensitivity_min_spinbox.setValue(0.2)
        self.sensitivity_min_slider.valueChanged.connect(lambda val: self.sensitivity_min_spinbox.setValue(val / 100.0))
        self.sensitivity_min_spinbox.valueChanged.connect(lambda val: self.sensitivity_min_slider.setValue(int(val * 100)))
        self.sensitivity_min_spinbox.valueChanged.connect(self.process_image)

        # 灵敏度上限
        self.sensitivity_max_label = QLabel("Sensitivity Max:")
        self.sensitivity_max_label.setToolTip("识别灵敏度上限 (0.0 ~ 1.0)。")
        self.sensitivity_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_max_slider.setRange(0, 100)
        self.sensitivity_max_slider.setValue(90)
        self.sensitivity_max_spinbox = QDoubleSpinBox()
        self.sensitivity_max_spinbox.setRange(0.0, 1.0)
        self.sensitivity_max_spinbox.setSingleStep(0.01)
        self.sensitivity_max_spinbox.setValue(0.9)
        self.sensitivity_max_slider.valueChanged.connect(lambda val: self.sensitivity_max_spinbox.setValue(val / 100.0))
        self.sensitivity_max_spinbox.valueChanged.connect(lambda val: self.sensitivity_max_slider.setValue(int(val * 100)))
        self.sensitivity_max_spinbox.valueChanged.connect(self.process_image)

        # 模糊半径
        self.blur_label = QLabel("Blur Radius:")
        self.blur_label.setToolTip("用于计算局部背景亮度的模糊半径。\n该值应大于要识别的最大粒子的半径。")
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(1, 100)
        self.blur_slider.setValue(8)
        self.blur_spinbox = QDoubleSpinBox()
        self.blur_spinbox.setRange(1, 100)
        self.blur_spinbox.setSingleStep(1)
        self.blur_spinbox.setValue(8)
        self.blur_slider.valueChanged.connect(self.blur_spinbox.setValue)
        self.blur_spinbox.valueChanged.connect(lambda val: self.blur_slider.setValue(int(val)))
        self.blur_spinbox.valueChanged.connect(self.process_image)

        # 边框宽度
        self.border_label = QLabel("Border Width:")
        self.border_label.setToolTip("要忽略的图像边框宽度（像素）。\n此区域内的任何内容都不会被标记。")
        self.border_slider = QSlider(Qt.Orientation.Horizontal)
        self.border_slider.setRange(0, 100)
        self.border_slider.setValue(2)
        self.border_spinbox = QDoubleSpinBox()
        self.border_spinbox.setRange(0, 100)
        self.border_spinbox.setSingleStep(1)
        self.border_spinbox.setValue(2)
        self.border_slider.valueChanged.connect(self.border_spinbox.setValue)
        self.border_spinbox.valueChanged.connect(lambda val: self.border_slider.setValue(int(val)))
        self.border_spinbox.valueChanged.connect(self.process_image)

        params_layout.addWidget(self.sensitivity_min_label, 0, 0)
        params_layout.addWidget(self.sensitivity_min_slider, 0, 1)
        params_layout.addWidget(self.sensitivity_min_spinbox, 0, 2)
        params_layout.addWidget(self.sensitivity_max_label, 1, 0)
        params_layout.addWidget(self.sensitivity_max_slider, 1, 1)
        params_layout.addWidget(self.sensitivity_max_spinbox, 1, 2)
        params_layout.addWidget(self.blur_label, 2, 0)
        params_layout.addWidget(self.blur_slider, 2, 1)
        params_layout.addWidget(self.blur_spinbox, 2, 2)
        params_layout.addWidget(self.border_label, 3, 0)
        params_layout.addWidget(self.border_slider, 3, 1)
        params_layout.addWidget(self.border_spinbox, 3, 2)

        # --- 粒子大小筛选区域 ---
        size_params_group = QGroupBox("Particle Size Filter")
        size_params_layout = QGridLayout(size_params_group)
        self.min_size_label = QLabel("Min Particle Size:")
        self.min_size_label.setToolTip("标记的最小粒子面积（像素数）。\n设置为0则不限制。")
        self.min_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_size_slider.setRange(0, 1000)
        self.min_size_slider.setValue(0)
        self.min_size_spinbox = QDoubleSpinBox()
        self.min_size_spinbox.setRange(0, 10000)
        self.min_size_spinbox.setSingleStep(10)
        self.min_size_spinbox.setValue(0)
        self.min_size_slider.valueChanged.connect(self.min_size_spinbox.setValue)
        self.min_size_spinbox.valueChanged.connect(lambda val: self.min_size_slider.setValue(int(val)))
        self.min_size_spinbox.valueChanged.connect(self.process_image)

        self.max_size_label = QLabel("Max Particle Size:")
        self.max_size_label.setToolTip("标记的最大粒子面积（像素数）。\n设置为0则不限制。")
        self.max_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_size_slider.setRange(0, 10000)
        self.max_size_slider.setValue(0)
        self.max_size_spinbox = QDoubleSpinBox()
        self.max_size_spinbox.setRange(0, 100000)
        self.max_size_spinbox.setSingleStep(100)
        self.max_size_spinbox.setValue(0)
        self.max_size_slider.valueChanged.connect(self.max_size_spinbox.setValue)
        self.max_size_spinbox.valueChanged.connect(lambda val: self.max_size_slider.setValue(int(val)))
        self.max_size_spinbox.valueChanged.connect(self.process_image)

        size_params_layout.addWidget(self.min_size_label, 0, 0)
        size_params_layout.addWidget(self.min_size_slider, 0, 1)
        size_params_layout.addWidget(self.min_size_spinbox, 0, 2)
        size_params_layout.addWidget(self.max_size_label, 1, 0)
        size_params_layout.addWidget(self.max_size_slider, 1, 1)
        size_params_layout.addWidget(self.max_size_spinbox, 1, 2)

        # --- 批量处理区域 ---
        batch_group = QGroupBox("Batch Processing")
        batch_main_layout = QVBoxLayout(batch_group)

        # 文件夹选择行
        dir_layout = QHBoxLayout()
        self.output_dir_label = QLabel("Output Directory:")
        self.output_dir_line_edit = QLineEdit(os.path.abspath("output"))
        self.output_dir_line_edit.setReadOnly(True)
        self.output_dir_button = QPushButton("Browse...")
        self.output_dir_button.clicked.connect(self.select_output_directory)
        dir_layout.addWidget(self.output_dir_label)
        dir_layout.addWidget(self.output_dir_line_edit, 1)
        dir_layout.addWidget(self.output_dir_button)

        # 动作按钮行
        action_layout = QHBoxLayout()
        action_layout.addStretch() # 将按钮推到右侧
        action_layout.addWidget(self.batch_button)

        batch_main_layout.addLayout(dir_layout)
        batch_main_layout.addLayout(action_layout)

        # --- 主布局 ---
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0) # 占满整个窗口

        # 左侧：图像显示区
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        
        image_panels_layout = QHBoxLayout()
        image_panels_layout.addWidget(self.original_image_label, 1)
        image_panels_layout.addWidget(self.processed_image_label, 1)

        self.result_label = QLabel("Load an image and select a region to begin.")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Footer ---
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(10, 0, 10, 5)
        
        logo_label = QLabel()
        logo_label.setPixmap(QPixmap("public/images/logo.svg").scaled(96, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        logo_label.setObjectName("footerLogo")

        email_label = QLabel("作者邮箱: zhanghaozheng@mail.ustc.edu.cn")
        email_label.setObjectName("footerLabel")
        email_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 设置字体为楷体并加粗
        font = QFont("楷体", 10, QFont.Weight.Bold)
        email_label.setFont(font)
        
        footer_layout.addWidget(logo_label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(email_label)
        footer_layout.addStretch(1)

        image_layout.addLayout(image_panels_layout)
        image_layout.addWidget(self.result_label)
        image_layout.addLayout(footer_layout)

        # 右侧：控制面板
        control_panel = QWidget()
        control_panel.setObjectName("controlPanel")
        control_panel_layout = QVBoxLayout(control_panel)

        top_buttons_layout = QGridLayout()
        top_buttons_layout.addWidget(self.load_button, 0, 0)
        top_buttons_layout.addWidget(self.save_button, 0, 1)
        top_buttons_layout.addWidget(self.clear_button, 0, 2)
        top_buttons_layout.addWidget(self.help_button, 1, 0)
        top_buttons_layout.addWidget(self.theme_button, 1, 1)
        
        control_panel_layout.addLayout(top_buttons_layout)
        control_panel_layout.addWidget(params_group)
        control_panel_layout.addWidget(size_params_group)
        control_panel_layout.addWidget(batch_group)
        control_panel_layout.addStretch() # 将所有控件推到顶部

        # --- 分隔器，用于调整左右区域大小 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(image_container)
        splitter.addWidget(control_panel)
        splitter.setSizes([800, 400]) # 设置初始尺寸比例
        splitter.setHandleWidth(10)
        splitter.setObjectName("mainSplitter")

        main_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)

        # 初始化状态变量
        self.pil_image = None
        self.last_selection_box = None
        self.last_result_image = None

        # 初始化主题属性
        self.is_dark_theme = True
        self.dark_style = ""
        self.light_style = ""
        self.load_themes()
        self.toggle_theme() # 应用初始主题

    def load_themes(self):
        """
        从 .qss 文件中加载深色和浅色两种主题的样式表。
        """
        try:
            with open('src/style/style.qss', 'r') as f:
                self.dark_style = f.read()
            with open('src/style/style_light.qss', 'r') as f:
                self.light_style = f.read()
        except FileNotFoundError as e:
            print(f"加载样式表失败: {e}。请确保 style.qss 和 style_light.qss 文件位于 src/style 目录下。")

    def toggle_theme(self):
        """
        切换应用程序的深色和浅色主题。
        """
        if self.is_dark_theme:
            QApplication.instance().setStyleSheet(self.light_style)
        else:
            QApplication.instance().setStyleSheet(self.dark_style)
        self.is_dark_theme = not self.is_dark_theme

    def select_output_directory(self):
        """
        打开一个对话框，让用户选择批量处理结果的输出目录。
        """
        output_dir = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir_line_edit.text())
        if output_dir:
            self.output_dir_line_edit.setText(output_dir)

    def batch_process_images(self):
        """
        执行批量处理操作。
        """
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择要批量处理的图片", "", "Image Files (*.png *.jpg *.bmp)")
        if not file_paths:
            return

        output_dir = self.output_dir_line_edit.text()
        if not output_dir or not os.path.isdir(output_dir):
            self.result_label.setText("错误：无效或未选择输出目录。")
            return

        # 获取当前设置的参数
        sensitivity_min = self.sensitivity_min_spinbox.value()
        sensitivity_max = self.sensitivity_max_spinbox.value()
        blur_radius = int(self.blur_spinbox.value())
        border_width = int(self.border_spinbox.value())
        min_size = int(self.min_size_spinbox.value())
        max_size = int(self.max_size_spinbox.value()) if self.max_size_spinbox.value() > 0 else None

        # 创建并显示进度条
        progress = QProgressDialog("正在处理图片...", "取消", 0, len(file_paths), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(True)
        progress.setMinimumDuration(0)

        for i, file_path in enumerate(file_paths):
            progress.setValue(i)
            if progress.wasCanceled():
                break

            base_name = os.path.basename(file_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(output_dir, f"{name}_marked{ext}")
            
            try:
                mark_dark_particles_adaptive(
                    image_input=file_path,
                    sensitivity_min=sensitivity_min,
                    sensitivity_max=sensitivity_max,
                    output_path=output_path,
                    blur_radius=blur_radius,
                    border_width=border_width,
                    selection_box=self.last_selection_box,
                    min_particle_size=min_size,
                    max_particle_size=max_size
                )
            except Exception as e:
                print(f"处理 {file_path} 时出错: {e}")
        
        progress.setValue(len(file_paths))

    def pil_to_pixmap(self, pil_img):
        """
        将Pillow Image对象转换为QPixmap对象。

        Args:
            pil_img (PIL.Image.Image): Pillow图像对象。

        Returns:
            QPixmap: PyQt图像对象。
        """
        if pil_img is None:
            return QPixmap()
        qt_img = ImageQt(pil_img.convert("RGBA"))
        return QPixmap.fromImage(qt_img)

    def load_image(self):
        """
        打开文件对话框以加载新图像。
        """
        file_path, _ = QFileDialog.getOpenFileName(self, "打开图片", "", "Image Files (*.png *.jpg *.bmp)")
        if file_path:
            self.pil_image = Image.open(file_path)
            self.clear_selection(clear_image=False) # 重置状态但保留新图像
            self.original_image_label.setPixmap(self.pil_to_pixmap(self.pil_image))
            self.processed_image_label.setText("请选择一个区域进行处理。")
            self.result_label.setText("请选择一个区域开始分析。")

    def clear_selection(self, clear_image=True):
        """
        清除当前的选择和处理结果。

        Args:
            clear_image (bool): 是否同时清除已加载的图像。
        """
        self.last_selection_box = None
        self.last_result_image = None
        self.save_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        
        if clear_image and self.pil_image:
            self.original_image_label.setPixmap(self.pil_to_pixmap(self.pil_image))
        
        self.processed_image_label.setPixmap(QPixmap())
        self.processed_image_label.setText("请选择一个区域进行处理。")
        self.result_label.setText("粒子百分比: N/A | 粒子数量: N/A")

    def save_image(self):
        """
        保存处理后的图像到文件。
        """
        if not self.last_result_image:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "保存图片", "marked_result.png", "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)")
        if file_path:
            try:
                self.last_result_image.save(file_path)
                print(f"结果已保存至 {file_path}")
            except Exception as e:
                print(f"保存文件时出错: {e}")

    def process_image(self):
        """
        核心图像处理函数。根据当前参数处理选定区域或整个图像。
        """
        if not self.pil_image:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            selection_qrect = self.original_image_label.get_selection()
            
            if not selection_qrect.isNull() and selection_qrect.width() > 1 and selection_qrect.height() > 1:
                scaled_pixmap = self.original_image_label.pixmap()
                if scaled_pixmap.isNull():
                    return

                label_size = self.original_image_label.size()
                pixmap_size = scaled_pixmap.size()
                offset_x = (label_size.width() - pixmap_size.width()) / 2
                offset_y = (label_size.height() - pixmap_size.height()) / 2
                adj_rect = selection_qrect.translated(-int(offset_x), -int(offset_y))

                img_width, img_height = self.pil_image.size
                if pixmap_size.width() == 0 or pixmap_size.height() == 0:
                    return

                x_scale = img_width / pixmap_size.width()
                y_scale = img_height / pixmap_size.height()

                left = int(adj_rect.left() * x_scale)
                top = int(adj_rect.top() * y_scale)
                right = int(adj_rect.right() * x_scale)
                bottom = int(adj_rect.bottom() * y_scale)
                
                left, right = sorted((max(0, left), min(img_width, right)))
                top, bottom = sorted((max(0, top), min(img_height, bottom)))
                self.last_selection_box = (left, top, right, bottom)
            
            if not self.last_selection_box:
                return

            sensitivity_min = self.sensitivity_min_spinbox.value()
            sensitivity_max = self.sensitivity_max_spinbox.value()
            blur_radius = int(self.blur_spinbox.value())
            border_width = int(self.border_spinbox.value())
            min_size = int(self.min_size_spinbox.value())
            max_size = int(self.max_size_spinbox.value()) if self.max_size_spinbox.value() > 0 else None

            result_img, percentage, num_particles = mark_dark_particles_adaptive(
                image_input=self.pil_image.copy(),
                sensitivity_min=sensitivity_min,
                sensitivity_max=sensitivity_max,
                output_path='output/gui_marked_result.png',
                blur_radius=blur_radius,
                border_width=border_width,
                selection_box=self.last_selection_box,
                min_particle_size=min_size,
                max_particle_size=max_size
            )
            
            original_with_box = self.pil_image.copy()
            draw = ImageDraw.Draw(original_with_box)
            draw.rectangle(self.last_selection_box, outline="blue", width=3)

            self.last_result_image = result_img
            self.save_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            
            self.original_image_label.setPixmap(self.pil_to_pixmap(original_with_box))
            self.processed_image_label.setPixmap(self.pil_to_pixmap(result_img))
            self.result_label.setText(f"Particle Percentage: {percentage:.2f}%  |  Particle Count: {num_particles}")

        finally:
            QApplication.restoreOverrideCursor()

    def show_help(self):
        """
        显示一个包含程序使用说明的帮助对话框。
        """
        try:
            with open('README.md', 'r', encoding='utf-8') as f:
                help_text = f.read()

            dialog = QDialog(self)
            dialog.setWindowTitle("Help - 使用说明")
            dialog.setMinimumSize(800, 600)

            scroll_area = QScrollArea(dialog)
            scroll_area.setWidgetResizable(True)

            help_label = QLabel(help_text, dialog)
            help_label.setTextFormat(Qt.TextFormat.MarkdownText)
            help_label.setWordWrap(True)
            help_label.setOpenExternalLinks(True)
            help_label.setContentsMargins(10, 10, 10, 10)

            scroll_area.setWidget(help_label)

            layout = QVBoxLayout(dialog)
            layout.addWidget(scroll_area)
            dialog.setLayout(layout)

            dialog.setStyleSheet("""
                QDialog {
                    background-color: #f0f0f0;
                }
                QLabel {
                    color: #333;
                    background-color: #ffffff;
                }
                QScrollArea {
                    border: none;
                }
                QScrollBar:vertical {
                    border: 1px solid #cccccc;
                    background: #f0f0f0;
                    width: 15px;
                    margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:vertical {
                    background: #cccccc;
                    min-height: 20px;
                    border-radius: 7px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """)
            
            dialog.exec()

        except FileNotFoundError:
            QMessageBox.warning(self, "Error", "找不到帮助文件 (README.md)。")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())