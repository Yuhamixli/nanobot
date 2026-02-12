---
name: image_understander
description: 图片 OCR、内容识别与图像分析（EasyOCR + Tesseract）
metadata: {"nanobot":{"emoji":"🖼️","requires":{"bins":["python"]}}}
---

# 图片理解工具 (Image Understander)

## 工具简介

支持图片 OCR 文字提取、图像分析，适用于商网等渠道收到的图片消息。

**调用方式**：Agent 通过 exec 执行，需传入图片路径。当用户发送图片时，bridge 会将图片下载到本地并将路径传入 `media`，agent 可直接使用该路径。

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

### 方法1: 命令行（Agent 推荐）
```bash
# 脚本与 SKILL.md 同目录，可从 skills 列表的 location 推导路径
python <skill_dir>/image_understander.py <图片路径> [输出目录]
```

示例（workspace 下或安装包的 skills 目录）：
```bash
python "C:\Users\xxx\.nanobot\workspace\..\nanobot\skills\image_understander\image_understander.py" "C:\path\to\image.jpg"
```

### 方法2: Python 代码调用
```python
# 需将 nanobot 包所在目录加入 PYTHONPATH
from nanobot.skills.image_understander.image_understander import ImageUnderstander

understander = ImageUnderstander()
result = understander.analyze_image("图片路径", "输出目录")
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