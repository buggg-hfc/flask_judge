from flask import Flask, render_template, request, redirect
import subprocess
from datetime import datetime
import psutil
import json
from pathlib import Path
import webbrowser

MEMORY_LIMIT = 512  # 全局内存限制（单位：MB）
TIME_LIMIT = 1  # 全局时间限制（单位：s）

app = Flask(__name__)

# 设置上传文件保存的目录
UPLOAD_FOLDER = Path('uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 设置测试数据保存的目录
PROBLEMS_FOLDER = Path('problems')
app.config['PROBLEMS_FOLDER'] = PROBLEMS_FOLDER

# 允许上传的文件类型
ALLOWED_EXTENSIONS = {'cpp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    submissions = []
    log_files = list(Path('submission').glob('*.log'))
    for log_file in log_files:
        try:
            with open(log_file, 'r') as file:
                # 每个日志文件的第一行是评测时间，第二行是评测结果
                log_data = json.load(file)
                submissions.append({
                    'timestamp': log_data['timestamp'],
                    'filename': log_data['filename'],
                    'result': log_data['result']
                })
        except json.JSONDecodeError:
            print(f"Warning: Failed to parse {log_file} as JSON. Skipping this file.")
        except KeyError:
            print(f"Warning: {log_file} is missing required fields. Skipping this file.")

    # 按时间排序，确保最新的记录在前
    submissions.sort(key=lambda x: x['timestamp'], reverse=True)
    return render_template('index.html', submissions=submissions)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = file.filename
        # 确保上传目录存在
        if not UPLOAD_FOLDER.exists():
            UPLOAD_FOLDER.mkdir(parents=True)
        file_path = UPLOAD_FOLDER / filename
        file.save(file_path)
        # 编译cpp文件
        result = compile_and_test_cpp(file_path)

        # 保存评测结果
        # 确保submission目录存在
        submission_folder = Path('submission')
        if not submission_folder.exists():
            submission_folder.mkdir(parents=True)

        # 生成日志文件名
        timestamp_for_filename = datetime.now().strftime('%Y%m%d-%H%M%S')  # 用于文件名的日期+时间
        timestamp_for_log = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 用于日志内容的日期+时间
        filename_without_ext = file_path.stem  # 去掉扩展名的提交的文件名
        log_filename = f"{timestamp_for_filename}-{filename_without_ext}.log"  # 组合成日志文件名
        log_path = submission_folder / log_filename  # 日志文件的完整路径

        # 将评测时间和评测结果写入日志文件（JSON格式）
        log_data = {
            'timestamp': timestamp_for_log,
            'filename': filename,
            'result': result
        }

        with open(log_path, 'w') as log_file:
            json.dump(log_data, log_file, indent=4)

        return render_template('submission.html', result=result)
    else:
        return '文件错误：请检查你上传的文件是否为*.cpp文件。'


def compile_and_test_cpp(filepath):
    # 1. 检查上传文件名是否正确

    # 确保数据目录存在
    if not PROBLEMS_FOLDER.exists():
        PROBLEMS_FOLDER.mkdir(parents=True)

    # 获取提交的cpp文件名
    filename = filepath.name
    subfolder = filename.split('.')[0]

    # 查找子文件夹
    subfolder_path = PROBLEMS_FOLDER / subfolder

    # 检查子文件夹是否存在
    if not subfolder_path.exists():
        return f'文件错误：题目“{subfolder}”不存在，请检查你的文件命名是否正确。'

    # 2. 检查编译是否正确

    # 编译cpp文件
    compiled_file = filepath.with_suffix('.exe')
    compile_command = f".\\mingw64\\bin\\g++.exe {filepath} -o {compiled_file} -Wall -std=c++11 -O2"
    subprocess.run(compile_command, shell=True)

    # 检查编译是否成功
    if not compiled_file.exists():
        return '编译错误：你提交的代码编译失败，请在本地开发环境确认代码能否正确编译。'

    # 3. 运行代码

    # 查找所有的输入文件
    input_files = list(subfolder_path.glob('*.in'))

    # 设置内存限制
    memory_limit = MEMORY_LIMIT * 1024 * 1024  # 默认 512MB
    process = psutil.Process()

    # 对每个输入文件进行测试
    for input_file in input_files:
        # 3.1 检查内存使用量
        if process.memory_info().rss > memory_limit:
            return '内存超限：你提交的代码由于超过运行内存限制导致运行失败，请检查你是否创建了过大的数组，或者动态分配了过多的内存空间。'

        # 构建输出文件的完整路径
        output_file = input_file.with_suffix('.out')

        # 3.2 检查运行时限
        # 执行编译后的文件，将输入文件作为输入
        try:
            result = subprocess.run([compiled_file], stdin=open(input_file), stdout=subprocess.PIPE,
                                    text=True, timeout=TIME_LIMIT, check=True)
        except subprocess.TimeoutExpired:
            return '运行超时：你提交的代码由于超过 CPU 运行时间限制导致运行失败，请检查你的算法的时间复杂度等是否正确。'

        # 读取预期输出文件内容
        with open(output_file, 'r') as f:
            expected_output_lines = f.readlines()

        # 3.3 检查答案正确性
        actual_output_lines = result.stdout.splitlines()
        if len(actual_output_lines) != len(expected_output_lines):
            return '答案错误：你提交的代码没有正确通过样例或运行错误，请检查你的算法是否正确，是否忽略了某些边界情况等等。'
        for actual_line, expected_line in zip(actual_output_lines, expected_output_lines):
            if actual_line.rstrip() != expected_line.rstrip():
                return '答案错误：你提交的代码没有正确通过样例或运行错误，请检查你的算法是否正确，是否忽略了某些边界情况等等。'

    return '答案正确：你提交的代码运行正常，正确通过了样例（但不代表你的代码能通过最终测试数据）。'


if __name__ == '__main__':
    # 启动Flask应用，并在浏览器中打开
    app_port = 5000
    app_url = f'http://127.0.0.1:{app_port}/'
    app_thread = webbrowser.open_new_tab(app_url)
    app.run(port=app_port)
