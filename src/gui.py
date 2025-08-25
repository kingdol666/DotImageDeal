import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton,
                             QVBoxLayout, QWidget, QFileDialog, QHBoxLayout,
                             QSlider, QDoubleSpinBox, QFrame, QRubberBand,
                             QProgressDialog, QLineEdit, QGroupBox, QGridLayout, QSizePolicy)
from PyQt6.QtGui import QPixmap, QIcon, QPainter
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal
from PIL import Image, ImageDraw
from PIL.ImageQt import ImageQt
from main import mark_dark_particles_adaptive

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    # Constants for DWM API
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    DWMSBT_MAINWINDOW = 2  # Mica
    DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
    DWMSBT_TABBEDWINDOW = 4 # Tabbed Mica

class ScaledPixmapLabel(QLabel):
    """A QLabel that automatically scales its pixmap while preserving aspect ratio."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumSize(1, 1)
        self._unscaled_pixmap = QPixmap()

    def setPixmap(self, pixmap):
        self._unscaled_pixmap = pixmap
        self._update_scaled_pixmap()

    def pixmap(self):
        # This returns the SCALED pixmap currently being displayed
        return super().pixmap()

    def unscaled_pixmap(self):
        # This returns the ORIGINAL, unscaled pixmap
        return self._unscaled_pixmap

    def resizeEvent(self, event):
        self._update_scaled_pixmap()
        super().resizeEvent(event)

    def _update_scaled_pixmap(self):
        if self._unscaled_pixmap.isNull():
            super().setPixmap(QPixmap())
            return
        
        scaled = self._unscaled_pixmap.scaled(self.size(),
                                             Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
        super().setPixmap(scaled)

class ImageSelectionLabel(ScaledPixmapLabel):
    """A ScaledPixmapLabel that also handles rubber band selection."""
    selection_changed = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.selection_origin = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.unscaled_pixmap().isNull():
            self.selection_origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.selection_origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if not self.selection_origin.isNull() and not self.unscaled_pixmap().isNull():
            self.rubber_band.setGeometry(QRect(self.selection_origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.unscaled_pixmap().isNull():
            self.rubber_band.hide()
            self.selection_changed.emit()

    def get_selection(self):
        return self.rubber_band.geometry()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dark Particle Analyzer - 深色粒子分析器")
        self.setGeometry(100, 100, 1200, 700)
        self.setWindowIcon(QIcon("public\images\icon.svg"))

        # --- Frameless Window Setup ---
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.gripSize = 8
        self.grips = []

        # --- Custom Title Bar ---
        self.title_bar = self._create_title_bar()

        self.original_image_label = ImageSelectionLabel()
        self.original_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.original_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.original_image_label.selection_changed.connect(self.process_image)

        self.processed_image_label = ScaledPixmapLabel("Load an image and select a region to process.")
        self.processed_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processed_image_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.processed_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.load_button = QPushButton(" Load Image")
        self.load_button.clicked.connect(self.load_image)

        self.save_button = QPushButton(" Save Result")
        self.save_button.clicked.connect(self.save_image)
        self.save_button.setEnabled(False)
        
        self.clear_button = QPushButton(" Clear Selection")
        self.clear_button.clicked.connect(self.clear_selection)
        self.clear_button.setEnabled(False)

        self.batch_button = QPushButton(" Batch Process")
        self.batch_button.clicked.connect(self.batch_process_images)

        self.theme_button = QPushButton(" Toggle Theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        
        # Parameters Group
        params_group = QGroupBox("Processing Parameters")
        params_layout = QGridLayout(params_group)

        self.sensitivity_label = QLabel("Sensitivity:")
        self.sensitivity_label.setToolTip("识别灵敏度 (0.0 ~ 1.0)。\n数值越高，识别标准越宽松，标记的粒子越多。")
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(0, 100)
        self.sensitivity_slider.setValue(70)
        self.sensitivity_spinbox = QDoubleSpinBox()
        self.sensitivity_spinbox.setRange(0.0, 1.0)
        self.sensitivity_spinbox.setSingleStep(0.01)
        self.sensitivity_spinbox.setValue(0.7)
        self.sensitivity_slider.valueChanged.connect(lambda val: self.sensitivity_spinbox.setValue(val / 100.0))
        self.sensitivity_spinbox.valueChanged.connect(lambda val: self.sensitivity_slider.setValue(int(val * 100)))
        self.sensitivity_spinbox.valueChanged.connect(self.process_image)

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

        params_layout.addWidget(self.sensitivity_label, 0, 0)
        params_layout.addWidget(self.sensitivity_slider, 0, 1)
        params_layout.addWidget(self.sensitivity_spinbox, 0, 2)
        params_layout.addWidget(self.blur_label, 1, 0)
        params_layout.addWidget(self.blur_slider, 1, 1)
        params_layout.addWidget(self.blur_spinbox, 1, 2)
        params_layout.addWidget(self.border_label, 2, 0)
        params_layout.addWidget(self.border_slider, 2, 1)
        params_layout.addWidget(self.border_spinbox, 2, 2)

        # Particle Size Parameters
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

        # Batch Processing Group
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QHBoxLayout(batch_group)
        self.output_dir_label = QLabel("Output Directory:")
        self.output_dir_line_edit = QLineEdit(os.path.abspath("output"))
        self.output_dir_line_edit.setReadOnly(True)
        self.output_dir_button = QPushButton("Browse...")
        self.output_dir_button.clicked.connect(self.select_output_directory)
        batch_layout.addWidget(self.output_dir_label)
        batch_layout.addWidget(self.output_dir_line_edit, 1)
        batch_layout.addWidget(self.output_dir_button)
        batch_layout.addWidget(self.batch_button)

        # Layouts
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        main_layout.addWidget(self.title_bar)

        # Wrap main content in a container for styling and margins
        content_container = QWidget()
        content_container.setObjectName("contentContainer")
        main_layout.addWidget(content_container, 1)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 10, 10, 10) # Add some padding
        
        top_controls_layout = QHBoxLayout()
        top_controls_layout.addWidget(self.load_button)
        top_controls_layout.addWidget(self.save_button)
        top_controls_layout.addWidget(self.clear_button)
        top_controls_layout.addStretch()
        top_controls_layout.addWidget(self.theme_button)

        image_layout = QHBoxLayout()
        image_layout.addWidget(self.original_image_label, 1)
        image_layout.addWidget(self.processed_image_label, 1)
        
        self.result_label = QLabel("Load an image and select a region to begin.")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bottom_controls_layout = QHBoxLayout()
        bottom_controls_layout.addWidget(params_group, 1)
        bottom_controls_layout.addWidget(size_params_group, 1)

        content_layout.addLayout(top_controls_layout)
        content_layout.addLayout(image_layout)
        content_layout.addWidget(self.result_label)
        content_layout.addLayout(bottom_controls_layout)
        content_layout.addWidget(batch_group)
        
        self.setCentralWidget(central_widget)

        self.pil_image = None
        self.last_selection_box = None
        self.last_result_image = None

        # Theme properties
        self.is_dark_theme = True
        self.dark_style = ""
        self.light_style = ""
        self.background_pixmap = QPixmap("public/images/background.png") # Load background
        self.load_themes()
        self.toggle_theme() # Apply initial theme
        self._apply_blur_effect()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.background_pixmap.isNull():
            # Scale the pixmap to cover the entire window, cropping if necessary
            scaled_pixmap = self.background_pixmap.scaled(self.size(), 
                                                          Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                                          Qt.TransformationMode.SmoothTransformation)
            # Center the pixmap
            x = (self.width() - scaled_pixmap.width()) / 2
            y = (self.height() - scaled_pixmap.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled_pixmap)

    def _apply_blur_effect(self):
        if not sys.platform == "win32":
            return

        hwnd = int(self.winId())
        if not hwnd:
            return

        # Use ctypes to call DwmSetWindowAttribute
        dwmapi = ctypes.windll.dwmapi
        
        # Define the function signature
        dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmSetWindowAttribute.restype = wintypes.LONG # Use LONG instead of HRESULT

        # Set backdrop type to Mica
        backdrop_type = DWMSBT_MAINWINDOW
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(ctypes.c_int(backdrop_type)),
            ctypes.sizeof(ctypes.c_int)
        )

        # Set dark/light mode for title bar and border
        is_dark = 1 if self.is_dark_theme else 0
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(ctypes.c_int(is_dark)),
            ctypes.sizeof(ctypes.c_int)
        )

    def _create_title_bar(self):
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(5, 0, 0, 0)
        title_bar_layout.setSpacing(0)

        # Icon and Title
        icon_label = QLabel()
        icon_pixmap = QPixmap("public/images/icon.svg")
        icon_label.setPixmap(icon_pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title_label = QLabel(" Dark Particle Analyzer")
        title_label.setObjectName("titleLabel")

        title_bar_layout.addWidget(icon_label)
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        # Window control buttons
        self.minimize_button = QPushButton("—")
        self.maximize_button = QPushButton("🗖")
        self.close_button = QPushButton("✕")

        self.minimize_button.setObjectName("controlButton")
        self.maximize_button.setObjectName("controlButton")
        self.close_button.setObjectName("closeButton")

        self.minimize_button.clicked.connect(self.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximize)
        self.close_button.clicked.connect(self.close)

        for btn in [self.minimize_button, self.maximize_button, self.close_button]:
            btn.setFixedSize(40, 30)
            title_bar_layout.addWidget(btn)

        # Mouse move tracking
        self._is_moving = False
        self._start_pos = QPoint()
        title_bar.mousePressEvent = self._title_bar_press
        title_bar.mouseMoveEvent = self._title_bar_move
        title_bar.mouseReleaseEvent = self._title_bar_release

        return title_bar

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _title_bar_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_moving = True
            self._start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def _title_bar_move(self, event):
        if self._is_moving:
            self.move(event.globalPosition().toPoint() - self._start_pos)
            event.accept()

    def _title_bar_release(self, event):
        self._is_moving = False
        event.accept()

    def load_themes(self):
        try:
            with open('src/style/style.qss', 'r') as f:
                self.dark_style = f.read()
            with open('src/style/style_light.qss', 'r') as f:
                self.light_style = f.read()
        except FileNotFoundError as e:
            print(f"Error loading stylesheet: {e}. Make sure style.qss and style_light.qss are in the src directory.")

    def toggle_theme(self):
        if self.is_dark_theme:
            QApplication.instance().setStyleSheet(self.light_style)
        else:
            QApplication.instance().setStyleSheet(self.dark_style)
        self.is_dark_theme = not self.is_dark_theme
        self._apply_blur_effect() # Re-apply to update dark/light mode

    def select_output_directory(self):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir_line_edit.text())
        if output_dir:
            self.output_dir_line_edit.setText(output_dir)

    def batch_process_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Images for Batch Processing", "", "Image Files (*.png *.jpg *.bmp)")
        if not file_paths:
            return

        output_dir = self.output_dir_line_edit.text()
        if not output_dir or not os.path.isdir(output_dir):
            self.result_label.setText("Error: Invalid or no output directory selected.")
            return

        sensitivity = self.sensitivity_spinbox.value()
        blur_radius = int(self.blur_spinbox.value())
        border_width = int(self.border_spinbox.value())
        min_size = int(self.min_size_spinbox.value())
        max_size = int(self.max_size_spinbox.value()) if self.max_size_spinbox.value() > 0 else None

        progress = QProgressDialog("Processing images...", "Cancel", 0, len(file_paths), self)
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
                    sensitivity=sensitivity,
                    output_path=output_path,
                    blur_radius=blur_radius,
                    border_width=border_width,
                    selection_box=self.last_selection_box,  # 使用当前选择的区域
                    min_particle_size=min_size,
                    max_particle_size=max_size
                )
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                # Optionally, show an error message to the user
        
        progress.setValue(len(file_paths))

    def pil_to_pixmap(self, pil_img):
        if pil_img is None:
            return QPixmap()
        qt_img = ImageQt(pil_img.convert("RGBA"))
        return QPixmap.fromImage(qt_img)

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Image Files (*.png *.jpg *.bmp)")
        if file_path:
            self.pil_image = Image.open(file_path)
            self.clear_selection(clear_image=False) # Reset state but keep the new image
            self.original_image_label.setPixmap(self.pil_to_pixmap(self.pil_image))
            self.processed_image_label.setText("Select a region to process.")
            self.result_label.setText("Select a region to begin analysis.")

    def clear_selection(self, clear_image=True):
        self.last_selection_box = None
        self.last_result_image = None
        self.save_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        
        if clear_image and self.pil_image:
            # Restore the original pixmap without any selection box
            self.original_image_label.setPixmap(self.pil_to_pixmap(self.pil_image))
        
        self.processed_image_label.setPixmap(QPixmap())
        self.processed_image_label.setText("Select a region to process.")
        self.result_label.setText("Particle Percentage: N/A | Particle Count: N/A")

    def save_image(self):
        if not self.last_result_image:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", "marked_result.png", "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)")
        if file_path:
            try:
                self.last_result_image.save(file_path)
                print(f"Result saved to {file_path}")
            except Exception as e:
                print(f"Error saving file: {e}")

    def process_image(self):
        if not self.pil_image:
            return

        selection_qrect = self.original_image_label.get_selection()
        
        # If the signal is from a slider, the selection rect might be empty.
        # In that case, we should use the last known selection.
        if not selection_qrect.isNull() and selection_qrect.width() > 1 and selection_qrect.height() > 1:
            scaled_pixmap = self.original_image_label.pixmap()
            if scaled_pixmap.isNull(): return

            label_size = self.original_image_label.size()
            pixmap_size = scaled_pixmap.size()
            offset_x = (label_size.width() - pixmap_size.width()) / 2
            offset_y = (label_size.height() - pixmap_size.height()) / 2
            adj_rect = selection_qrect.translated(-int(offset_x), -int(offset_y))

            img_width, img_height = self.pil_image.size
            if pixmap_size.width() == 0 or pixmap_size.height() == 0: return
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
            # Even if there's no selection, we should still update the parameters
            # so that batch processing uses the latest values.
            return

        sensitivity = self.sensitivity_spinbox.value()
        blur_radius = int(self.blur_spinbox.value())
        border_width = int(self.border_spinbox.value())
        min_size = int(self.min_size_spinbox.value())
        max_size = int(self.max_size_spinbox.value()) if self.max_size_spinbox.value() > 0 else None

        result_img, percentage, num_particles = mark_dark_particles_adaptive(
            image_input=self.pil_image.copy(),
            sensitivity=sensitivity,
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

        # Store result for saving and display
        self.last_result_image = result_img
        self.save_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        
        # Display original with box, but keep the unscaled version for future selections
        self.original_image_label.setPixmap(self.pil_to_pixmap(original_with_box))
        self.processed_image_label.setPixmap(self.pil_to_pixmap(result_img))
        self.result_label.setText(f"Particle Percentage: {percentage:.2f}%  |  Particle Count: {num_particles}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
