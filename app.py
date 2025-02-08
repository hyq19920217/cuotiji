from flask import Flask, request, jsonify, render_template, make_response, send_file
from flask_sqlalchemy import SQLAlchemy
from aip import AipOcr
import os
from config import Config
import json
import traceback  # 添加到文件顶部
import requests
from PIL import Image, ImageDraw
import pillow_heif  # 需要添加这个库来支持 HEIF 格式
import io
from datetime import datetime
import pdfkit
from jinja2 import Template
import cv2
import numpy as np

app = Flask(__name__)
app.config.from_object(Config)

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# 定义错题模型
class Mistake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    tags = db.Column(db.Text)  # 存储JSON格式的标签列表
    analysis = db.Column(db.Text)  # 存储分析结果

# 初始化百度OCR客户端
ocr_client = AipOcr(app.config['BAIDU_APP_ID'],
                    app.config['BAIDU_API_KEY'],
                    app.config['BAIDU_SECRET_KEY'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_image():
    try:
        # 处理直接保存文本的情况
        if request.is_json:
            data = request.get_json()
            text = data.get('text')
            if not text:
                return jsonify({'error': '文本内容为空'}), 400
                
            # 保存到数据库
            mistake = Mistake(content=text)
            db.session.add(mistake)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'id': mistake.id
            })
        
        # 处理图片上传的情况
        if 'image' not in request.files:
            return jsonify({'error': '没有上传文件', 'detail': 'No image in request.files'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '没有选择文件', 'detail': 'No filename'}), 400
        
        if file:
            # 获取文件扩展名
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            # 保存文件
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            
            # 如果是 HEIF/HEIC 格式，转换为 JPEG
            if file_ext in ['heif', 'heic']:
                try:
                    # 读取 HEIF 图片
                    heif_file = pillow_heif.read_heif(filename)
                    # 转换为 PIL Image
                    image = Image.frombytes(
                        heif_file.mode, 
                        heif_file.size, 
                        heif_file.data,
                        "raw",
                    )
                    # 转换为 JPEG 并保存
                    jpeg_filename = filename.rsplit('.', 1)[0] + '.jpg'
                    image.save(jpeg_filename, 'JPEG')
                    filename = jpeg_filename  # 更新文件名为转换后的 JPEG 文件
                except Exception as e:
                    return jsonify({'error': 'HEIF 转换失败', 'detail': str(e)}), 500
            
            # 使用高精度文字识别
            options = {
                "detect_direction": "true",
                "probability": "true",       # 返回置信度
                "vertexes_location": "true"  # 返回文字位置
            }
            
            print("开始调用百度 OCR...")
            result = ocr_client.accurate(filename, options)
            print("OCR 返回结果:", result)
            
            if 'error_code' in result:
                raise Exception(result.get('error_msg', '识别失败'))
            
            # 处理识别结果
            img = Image.open(filename).convert('RGB')
            draw = ImageDraw.Draw(img)
            
            # 用白色填充低置信度的区域（可能是手写）
            for word_info in result['words_result']:
                probability = float(word_info['probability']['average'])
                if probability < 0.85:  # 低置信度可能是手写
                    # 获取文字区域坐标
                    location = word_info['location']
                    # 用白色填充
                    draw.rectangle([
                        location['left'], location['top'],
                        location['left'] + location['width'],
                        location['top'] + location['height']
                    ], fill='white')
                    print(f"移除低置信度文字: {word_info['words']}, 置信度: {probability}")
            
            # 保存到内存
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            return send_file(
                io.BytesIO(img_byte_arr),
                mimetype='image/png',
                as_attachment=False
            )
    
    except Exception as e:
        return jsonify({'error': '处理失败', 'detail': str(e)}), 500
    
    return jsonify({'error': '未知错误'}), 500

@app.route('/api/mistakes', methods=['GET'])
def get_mistakes():
    mistakes = Mistake.query.order_by(Mistake.created_at.desc()).all()
    return jsonify([{
        'id': m.id,
        'content': m.content,
        'image_path': m.image_path,
        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'tags': json.loads(m.tags) if m.tags else [],  # 添加标签
        'analysis': m.analysis  # 添加分析结果
    } for m in mistakes])

@app.route('/api/mistakes/<int:mistake_id>', methods=['PUT'])
def update_mistake(mistake_id):
    try:
        data = request.get_json()
        mistake = Mistake.query.get_or_404(mistake_id)
        mistake.content = data['content']
        db.session.commit()
        return jsonify({
            'success': True,
            'mistake': {
                'id': mistake.id,
                'content': mistake.content,
                'created_at': mistake.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        return jsonify({'error': '更新失败', 'detail': str(e)}), 500

@app.route('/api/mistakes/<int:mistake_id>', methods=['DELETE'])
def delete_mistake(mistake_id):
    try:
        mistake = Mistake.query.get_or_404(mistake_id)
        db.session.delete(mistake)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': '删除失败', 'detail': str(e)}), 500

@app.route('/api/mistakes/analyze', methods=['POST'])
def analyze_mistakes():
    try:
        data = request.get_json()
        mistake_ids = data.get('mistake_ids', [])
        
        mistakes = Mistake.query.filter(Mistake.id.in_(mistake_ids)).all()
        results = []
        
        for mistake in mistakes:
            # 如果已经有分析结果且不需要刷新，直接返回
            if mistake.analysis and mistake.tags and not data.get('refresh', False):
                results.append({
                    'id': mistake.id,
                    'tags': json.loads(mistake.tags),
                    'analysis': mistake.analysis
                })
                continue
                
            # 调用 API 进行分析
            system_prompt = """
            你是一个教育专家。请分析题目并提取知识点，以 JSON 格式输出。输出应包含以下字段：
            - tags: 知识点标签数组
            - analysis: 详细分析
            """
            
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f'请分析以下题目：\n{mistake.content}'}
            ]
            
            response = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {app.config["DEEPSEEK_API_KEY"]}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'deepseek-chat',
                    'messages': [{
                        'role': msg['role'],
                        'content': msg['content'].strip()
                    } for msg in messages],
                    'temperature': 0.7,
                    'response_format': {'type': 'json_object'},
                    'max_tokens': 2000  # 防止 JSON 被截断
                }
            )
            
            # 把日志移到这里
            print(f"请求 URL: {response.request.url}")
            print(f"请求头: {response.request.headers}")
            print(f"请求体: {response.request.body}")
            print(f"响应状态码: {response.status_code}")
            print(f"模型返回的原始响应: {response.text}")
            
            try:
                result = response.json()
                print(f"解析后的结果: {result}")
                
                if 'error' in result:
                    raise ValueError(f"API 错误: {result['error']}")
                
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0].get('message', {}).get('content', '')
                    if not content:
                        raise ValueError("API 返回了空的内容")
                    
                    # 解析 JSON 响应
                    parsed = json.loads(content)
                    analysis = parsed['analysis']
                    tags = parsed['tags']
                else:
                    print(f"未知的响应格式: {result}")
                    raise ValueError(f"未知的响应格式: {result}")
                
                print(f"成功提取分析结果: {analysis}")
                print(f"提取的标签: {tags}")
                
                # 保存分析结果到数据库
                mistake.analysis = analysis
                mistake.tags = json.dumps(tags, ensure_ascii=False)
                results.append({
                    'id': mistake.id,
                    'tags': tags,
                    'analysis': analysis
                })
            except Exception as e:
                print(f"解析响应失败: {str(e)}")
                raise Exception(f"解析模型响应失败: {str(e)}")

            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'成功分析 {len(mistakes)} 道题目',
            'results': results  # 只返回分析结果
        })
        
    except Exception as e:
        error_detail = str(e)
        print(f"分析错误: {error_detail}")
        return jsonify({
            'error': '分析失败', 
            'detail': error_detail,
            'traceback': traceback.format_exc()
        }), 500

@app.route('/api/mistakes', methods=['POST'])
def create_mistake():
    try:
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({'error': '内容不能为空'}), 400
            
        # 保存到数据库
        mistake = Mistake(content=content)
        db.session.add(mistake)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': mistake.id,
            'message': '保存成功'
        })
        
    except Exception as e:
        print(f"创建错题失败: {str(e)}")  # 添加日志
        return jsonify({
            'error': '保存失败',
            'detail': str(e)
        }), 500

def extract_tags(analysis):
    # 简单的标签提取逻辑
    # 这里可以根据实际的返回格式调整
    tags = []
    for line in analysis.split('\n'):
        if line.strip().startswith('#') or line.strip().startswith('- '):
            tag = line.strip().replace('#', '').replace('- ', '').strip()
            if tag:
                tags.append(tag)
    return tags

@app.route('/api/mistakes/batch-delete', methods=['POST'])
def batch_delete_mistakes():
    try:
        data = request.get_json()
        mistake_ids = data.get('mistake_ids', [])
        
        if not mistake_ids:
            return jsonify({'error': '没有选择要删除的错题'}), 400
            
        # 批量删除
        Mistake.query.filter(Mistake.id.in_(mistake_ids)).delete(synchronize_session=False)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'成功删除 {len(mistake_ids)} 条记录'
        })
        
    except Exception as e:
        print(f"批量删除失败: {str(e)}")
        return jsonify({
            'error': '删除失败',
            'detail': str(e)
        }), 500

@app.route('/api/mistakes/export', methods=['POST'])
def export_mistakes():
    try:
        data = request.get_json()
        mistake_ids = data.get('mistake_ids', [])
        export_type = data.get('export_type', 'questions')
        
        if not mistake_ids:
            return jsonify({'error': '没有选择要导出的错题'}), 400
            
        mistakes = Mistake.query.filter(Mistake.id.in_(mistake_ids)).all()
        
        # 准备 HTML 模板
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; }
                .mistake { margin-bottom: 30px; page-break-inside: avoid; }
                .content { white-space: pre-wrap; margin: 10px 0; }
                .analysis { margin-top: 10px; background: #f5f5f5; padding: 10px; }
                .tags { margin-top: 10px; }
                .tag { display: inline-block; margin: 2px; padding: 2px 8px; background: #eee; border-radius: 12px; }
            </style>
        </head>
        <body>
            <h1>错题集</h1>
            <p>导出时间：{{ export_time }}</p>
            {% for mistake in mistakes %}
            <div class="mistake">
                <h3>错题 {{ loop.index }}</h3>
                <div class="content">{{ mistake.content }}</div>
                {% if export_type == 'full' and mistake.analysis %}
                <div class="analysis">
                    <h4>分析结果：</h4>
                    <div>{{ mistake.analysis }}</div>
                    {% if mistake.tags %}
                    <div class="tags">
                        <h4>知识点标签：</h4>
                        {% for tag in tags[loop.index0] %}
                        <span class="tag">{{ tag }}</span>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </body>
        </html>
        """
        
        # 准备模板数据
        template_data = {
            'mistakes': mistakes,
            'export_type': export_type,
            'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tags': [json.loads(m.tags) if m.tags else [] for m in mistakes]
        }
        
        # 渲染 HTML
        template = Template(html_template)
        html_content = template.render(**template_data)
        
        # 生成 PDF
        pdf = pdfkit.from_string(html_content, False)
        
        # 准备响应
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=mistakes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        return response
        
    except Exception as e:
        print(f"导出错误: {str(e)}")
        return jsonify({
            'error': '导出失败',
            'detail': str(e)
        }), 500

@app.route('/api/process-image', methods=['POST'])
def process_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['image']
        image = file.read()
        
        # 使用高精度文字识别
        options = {
            "detect_direction": "true",
            "probability": "true",       # 返回置信度
            "vertexes_location": "true"  # 返回文字位置
        }
        
        print("开始调用百度 OCR...", flush=True)
        print(f"使用的配置: APP_ID={app.config['BAIDU_APP_ID']}", flush=True)
        result = ocr_client.accurate(image, options)
        print("OCR 返回结果:", result, flush=True)
        
        if 'error_code' in result:
            print(f"百度 OCR 返回错误: {result}", flush=True)
            raise Exception(result.get('error_msg', '识别失败'))
            
        # 处理识别结果
        try:
            img = Image.open(io.BytesIO(image)).convert('RGB')
            draw = ImageDraw.Draw(img)
            
            # 用白色填充低置信度的区域（可能是手写）
            for word_info in result['words_result']:
                try:
                    probability = float(word_info['probability']['average'])
                    if probability < 0.85:  # 低置信度可能是手写
                        location = word_info['location']
                        draw.rectangle([
                            location['left'], location['top'],
                            location['left'] + location['width'],
                            location['top'] + location['height']
                        ], fill='white')
                        print(f"移除低置信度文字: {word_info['words']}, 置信度: {probability}", flush=True)
                except Exception as e:
                    print(f"处理单个文字区域时出错: {str(e)}", flush=True)
                    continue
                    
        except Exception as e:
            print(f"图像处理过程出错: {str(e)}", flush=True)
            raise
        
        # 保存到内存
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        return send_file(
            io.BytesIO(img_byte_arr),
            mimetype='image/png',
            as_attachment=False
        )
        
    except Exception as e:
        print(f"图像处理错误: {str(e)}", flush=True)
        print(f"错误详情: {traceback.format_exc()}", flush=True)
        return jsonify({
            'error': '图像处理失败',
            'detail': str(e),
            'traceback': traceback.format_exc()
        }), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=8000, debug=True) 