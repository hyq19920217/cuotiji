from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from aip import AipOcr
import os
from config import Config
import json
import traceback  # 添加到文件顶部
import requests

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
    analysis = db.Column(db.Text)  # 存储大模型的分析结果

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
        if 'image' not in request.files:
            return jsonify({'error': '没有上传文件', 'detail': 'No image in request.files'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '没有选择文件', 'detail': 'No filename'}), 400
        
        if file:
            # 保存文件
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            try:
                file.save(filename)
            except Exception as e:
                return jsonify({'error': '文件保存失败', 'detail': str(e)}), 500
            
            # 读取图片文件
            try:
                with open(filename, 'rb') as fp:
                    image = fp.read()
            except Exception as e:
                return jsonify({'error': '文件读取失败', 'detail': str(e)}), 500
                    
            # 调用百度OCR API
            try:
                print("开始调用百度OCR API...")
                result = ocr_client.basicGeneral(image)  # 基础版本
                print("OCR 原始返回结果:", result)  # 打印完整返回结果
                
                # 检查 API Key 是否正确加载
                print("当前使用的百度OCR配置:")
                print(f"APP_ID: {app.config['BAIDU_APP_ID']}")
                print(f"API_KEY: {app.config['BAIDU_API_KEY']}")
                print(f"SECRET_KEY: {app.config['BAIDU_SECRET_KEY'][:10]}...")  # 只打印前10位
                
                if 'error_code' in result:
                    error_msg = f"OCR错误: {result.get('error_msg', '未知错误')}"
                    print(error_msg)
                    return jsonify({'error': '识别失败', 'detail': error_msg}), 500
            except Exception as e:
                print(f"OCR Exception: {str(e)}")
                return jsonify({'error': 'OCR处理失败', 'detail': str(e)}), 500
            
            if 'words_result' in result:
                print("识别到的文字数量:", len(result['words_result']))
                # 直接使用识别结果
                text = '\n'.join(item['words'] for item in result['words_result'])
                print(f"处理后的文本:\n{text}")  # 添加日志
                
                try:
                    # 保存到数据库
                    mistake = Mistake(content=text, image_path=filename)
                    print(f"准备保存到数据库: content={text}, image_path={filename}")  # 添加日志
                    db.session.add(mistake)
                    db.session.commit()
                    print("数据库保存成功")  # 添加日志
                except Exception as e:
                    print(f"数据库保存失败: {str(e)}")  # 添加详细错误信息
                    return jsonify({'error': '数据库保存失败', 'detail': str(e)}), 500
                
                return jsonify({
                    'success': True,
                    'text': text,
                    'id': mistake.id
                })
    
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
        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S')
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
        
        for mistake in mistakes:
            system_prompt = """
            你是一个教育专家。请分析题目并提取知识点，以 JSON 格式输出。输出应包含以下字段：
            - tags: 知识点标签数组
            - analysis: 详细分析
            
            示例输出：
            {
                "tags": ["代数", "一元二次方程", "因式分解"],
                "analysis": "这道题目涉及一元二次方程的求解，需要使用因式分解方法..."
            }
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
                
                # 更新数据库
                mistake.analysis = analysis
                mistake.tags = json.dumps(tags, ensure_ascii=False)
            except Exception as e:
                print(f"解析响应失败: {str(e)}")
                raise Exception(f"解析模型响应失败: {str(e)}")

            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'成功分析 {len(mistakes)} 道题目'
            })
        
    except Exception as e:
        error_detail = str(e)
        print(f"分析错误: {error_detail}")  # 添加日志
        return jsonify({
            'error': '分析失败', 
            'detail': error_detail,
            'traceback': traceback.format_exc()  # 添加完整的错误堆栈
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 