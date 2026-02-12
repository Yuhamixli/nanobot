#!/usr/bin/env python3
"""
图片理解工具
支持图片内容识别、OCR文字提取、图像分析等功能
"""

import os
import sys
import base64
from PIL import Image
import easyocr
import cv2
import numpy as np
import pytesseract
from io import BytesIO

class ImageUnderstander:
    def __init__(self):
        """初始化图片理解器"""
        try:
            # 初始化EasyOCR，支持中英文
            self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            print("EasyOCR 初始化成功")
        except Exception as e:
            print(f"EasyOCR 初始化失败: {e}")
            self.reader = None
            
    def analyze_image(self, image_path, output_dir=None):
        """分析图片内容"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                return {"error": f"图片文件不存在: {image_path}"}
            
            # 读取图片
            image = Image.open(image_path)
            print(f"图片信息: {image.size} 像素, 模式: {image.mode}")
            
            # 基础信息
            result = {
                "basic_info": {
                    "size": image.size,
                    "mode": image.mode,
                    "format": image.format,
                    "width": image.width,
                    "height": image.height
                },
                "ocr_text": [],
                "analysis": {}
            }
            
            # OCR文字识别
            if self.reader:
                try:
                    ocr_results = self.reader.readtext(image_path, detail=0)
                    result["ocr_text"] = ocr_results
                    print(f"OCR识别到 {len(ocr_results)} 条文字")
                except Exception as e:
                    print(f"OCR识别失败: {e}")
                    result["ocr_error"] = str(e)
            
            # 尝试使用pytesseract进行补充OCR
            try:
                # 转换为OpenCV格式
                cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                # 使用pytesseract识别英文
                tess_text = pytesseract.image_to_string(cv_image, lang='chi_sim+eng')
                if tess_text.strip():
                    result["tesseract_text"] = tess_text.strip()
            except Exception as e:
                print(f"Tesseract OCR失败: {e}")
                result["tesseract_error"] = str(e)
            
            # 图像分析
            result["analysis"] = self._analyze_image_content(image)
            
            # 保存分析结果到文件
            if output_dir:
                self._save_analysis_result(result, output_dir, os.path.basename(image_path))
            
            return result
            
        except Exception as e:
            return {"error": f"图片分析失败: {str(e)}"}
    
    def _analyze_image_content(self, image):
        """分析图片内容"""
        analysis = {}
        
        try:
            # 转换为numpy数组
            img_array = np.array(image)
            
            # 颜色分析
            if len(img_array.shape) == 3:
                # 计算平均颜色
                avg_color = np.mean(img_array, axis=(0, 1))
                analysis["avg_color"] = {
                    "blue": int(avg_color[0]),
                    "green": int(avg_color[1]), 
                    "red": int(avg_color[2])
                }
                
                # 检测主要颜色
                pixels = img_array.reshape(-1, 3)
                unique_colors = np.unique(pixels, axis=0)
                analysis["unique_colors_count"] = len(unique_colors)
                
            # 亮度分析
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
                
            brightness = np.mean(gray)
            analysis["brightness"] = float(brightness)
            
            # 对比度分析
            contrast = np.std(gray)
            analysis["contrast"] = float(contrast)
            
            # 检测边缘
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            analysis["edge_density"] = float(edge_density)
            
        except Exception as e:
            analysis["error"] = str(e)
            
        return analysis
    
    def _save_analysis_result(self, result, output_dir, image_name):
        """保存分析结果"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 保存为文本文件
            output_file = os.path.join(output_dir, f"{os.path.splitext(image_name)[0]}_analysis.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"图片分析结果: {image_name}\n")
                f.write("=" * 50 + "\n\n")
                
                # 基础信息
                f.write("基础信息:\n")
                for key, value in result["basic_info"].items():
                    f.write(f"  {key}: {value}\n")
                f.write("\n")
                
                # OCR结果
                if result["ocr_text"]:
                    f.write("OCR识别文字:\n")
                    for i, text in enumerate(result["ocr_text"], 1):
                        f.write(f"  {i}. {text}\n")
                    f.write("\n")
                
                # Tesseract结果
                if "tesseract_text" in result:
                    f.write("Tesseract识别文字:\n")
                    f.write(f"  {result['tesseract_text']}\n\n")
                
                # 图像分析
                f.write("图像分析:\n")
                for key, value in result["analysis"].items():
                    f.write(f"  {key}: {value}\n")
                    
        except Exception as e:
            print(f"保存分析结果失败: {e}")

def main():
    """主函数 - 命令行工具"""
    if len(sys.argv) < 2:
        print("使用方法: python image_understander.py <图片路径> [输出目录]")
        return
    
    image_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "analysis_results"
    
    # 创建图片理解器
    understander = ImageUnderstander()
    
    # 分析图片
    print(f"开始分析图片: {image_path}")
    result = understander.analyze_image(image_path, output_dir)
    
    # 输出结果
    if "error" in result:
        print(f"错误: {result['error']}")
        return
    
    print("\n分析完成!")
    print(f"图片尺寸: {result['basic_info']['width']}x{result['basic_info']['height']}")
    
    if result["ocr_text"]:
        print(f"识别到 {len(result['ocr_text'])} 条文字:")
        for i, text in enumerate(result["ocr_text"], 1):
            print(f"  {i}. {text}")
    
    if "tesseract_text" in result:
        print(f"\nTesseract补充识别:")
        print(f"  {result['tesseract_text']}")
    
    print(f"\n详细结果已保存到: {output_dir}")

if __name__ == "__main__":
    main()