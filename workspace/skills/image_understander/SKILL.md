# 图片理解工具 (Image Understander)

## 工具简介

这是一个强大的图片理解工具，支持图片内容识别、OCR文字提取、图像分析等功能。

## 功能特性

### 🔍 核心功能
- **图片内容识别**：自动分析图片基本信息
- **OCR文字识别**：支持中英文文字提取
- **图像分析**：颜色、亮度、对比度、边缘密度分析
- **结果保存**：分析结果自动保存为文本文件

### 📊 分析维度
1. **基础信息**：尺寸、模式、格式等
2. **OCR文字**：EasyOCR + Tesseract双重识别
3. **颜色分析**：平均颜色、唯一颜色数量
4. **亮度对比度**：图片明暗程度和对比度
5. **边缘检测**：图片复杂度分析

## 使用方法

### 方法1: 命令行使用
```bash
python skills/image_understander/image_understander.py <图片路径> [输出目录]
```

### 方法2: Python代码调用
```python
from skills.image_understander.image_understander import ImageUnderstander

# 创建图片理解器
understander = ImageUnderstander()

# 分析图片
result = understander.analyze_image("图片路径", "输出目录")

# 查看结果
print(result)
```

## 输出示例

```
图片分析结果: example.jpg
==================================================

基础信息:
  size: (1920, 1080)
  mode: RGB
  format: JPEG
  width: 1920
  height: 1080

OCR识别文字:
  1. 欢迎来到北京
  2. Beijing Welcome

Tesseract识别文字:
  Welcome to Beijing

图像分析:
  avg_color: {'blue': 45, 'green': 120, 'red': 180}
  unique_colors_count: 15420
  brightness: 128.5
  contrast: 45.2
  edge_density: 0.156
```

## 技术特性

- **双重OCR引擎**：EasyOCR (支持复杂场景) + Tesseract (标准OCR)
- **多语言支持**：中文简体、英文自动识别
- **智能分析**：自动检测图片特征和复杂度
- **错误处理**：完善的异常处理机制

## 依赖库

- `pillow`: 图片处理
- `easyocr`: 深度学习OCR
- `opencv-python-headless`: 计算机视觉
- `pytesseract`: 标准OCR
- `numpy`: 数值计算

## 注意事项

1. **首次运行**：EasyOCR需要下载模型文件，首次使用可能较慢
2. **图片格式**：支持常见格式（JPG、PNG、BMP等）
3. **文件路径**：确保图片路径正确且有读取权限
4. **输出目录**：会自动创建不存在的目录

## 适用场景

- 📸 **图片内容识别**：快速提取图片中的文字信息
- 🔍 **图像质量分析**：评估图片的视觉效果
- 📝 **文档数字化**：将图片中的文字转换为可编辑文本
- 🎨 **图片特征分析**：了解图片的色彩和复杂度特征

---

**开发状态**: ✅ 已完成并可用  
**版本**: 1.0  
**兼容性**: Python 3.7+