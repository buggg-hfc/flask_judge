from flask import Flask, render_template, request, redirect
import subprocess
from datetime import datetime
import psutil
import json
from pathlib import Path
import webbrowser
import re

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
            pass
            # print(f"Warning: Failed to parse {log_file} as JSON. Skipping this file.")
        except KeyError:
            pass
            # print(f"Warning: {log_file} is missing required fields. Skipping this file.")

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
        result = compile_and_test_cpp(file_path, PROBLEMS_FOLDER, MEMORY_LIMIT, TIME_LIMIT)

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


def preprocess_and_check_code(filepath):
    """
    宏展开代码，并进行简单的安全检查。
    """
    # 使用 GCC 进行宏展开
    preprocess_command = f".\\mingw64\\bin\\g++.exe -E {filepath}"
    try:
        preprocessed_code = subprocess.check_output(preprocess_command, shell=True).decode()
        print('debug:', preprocessed_code)
    except subprocess.CalledProcessError:
        return False

    # 检查宏展开后的代码中是否存在潜在的危险指令
    dangerous_patterns = [
        r'system\s*\(\"',
        r'exec\s*\(\"'
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, preprocessed_code):
            return False  # 发现潜在危险指令

    return True


def compile_and_test_cpp(filepath, problems_folder=PROBLEMS_FOLDER, memory_limit_mb=512, time_limit_sec=1):
    """
    编译并测试 C++ 程序。

    参数:
    - filepath: 提交的 C++ 源代码文件的路径。
    - problems_folder: 包含测试数据的目录路径。
    - memory_limit_mb: 允许程序使用的最大内存（以 MB 为单位）。
    - time_limit_sec: 允许程序运行的最大时间（以秒为单位）。

    返回:
    - 一个字符串，描述测试结果。
    """

    # 1. 检查上传文件名是否正确

    # 确保数据目录存在
    problems_path = Path(problems_folder)
    if not problems_path.exists():
        return '内部错误：测试数据目录不存在。'

    # 获取提交的cpp文件名
    filename = filepath.name
    subfolder = filename.rsplit('.', 1)[0]
    subfolder_path = problems_path / subfolder

    # 检查子文件夹是否存在
    if not subfolder_path.exists():
        return f'文件错误：题目“{subfolder}”不存在，请检查你的文件命名是否正确。'

    # 预处理并检查代码
    if not preprocess_and_check_code(filepath):
        return '拒绝编译：检测到潜在的危险操作。'

    # 2. 检查编译是否正确

    # 编译cpp文件
    compiled_file = filepath.with_suffix('.exe')
    compile_command = f".\\mingw64\\bin\\g++.exe {filepath} -o {compiled_file} -Wall -std=c++11 -O2"
    compile_result = subprocess.run(compile_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 检查编译是否成功
    if compile_result.returncode != 0:
        return '编译错误：你提交的代码编译失败，请在本地开发环境确认代码能否正确编译。'

    # 3. 运行代码

    # 对每个输入文件进行测试
    for input_file in subfolder_path.glob('*.in'):
        output_file = input_file.with_suffix('.result')

        with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
            start_time = datetime.now()
            proc = subprocess.Popen([compiled_file], stdin=infile, stdout=outfile)

            # 监控内存使用
            peak_memory = 0
            try:
                while True:
                    if proc.poll() is not None:  # 检查进程是否已结束
                        break
                    proc_memory = psutil.Process(proc.pid).memory_info().rss
                    if proc_memory > peak_memory:
                        peak_memory = proc_memory
                    if peak_memory > memory_limit_mb * 1024 * 1024:
                        proc.kill()
                        return '内存超限：你提交的代码由于超过运行内存限制导致运行失败，请检查你是否创建了过大的数组，或者动态分配了过多的内存空间。'

                    # 检查是否超时
                    if (datetime.now() - start_time).seconds > time_limit_sec:
                        proc.kill()
                        return '运行超时：你提交的代码由于超过 CPU 运行时间限制导致运行失败，请检查你的算法的时间复杂度等是否正确。'
            except psutil.NoSuchProcess:
                pass

        expected_output_file = input_file.with_suffix('.out')

        # 3.3 检查答案正确性
        with open(output_file, 'r') as f_out, open(expected_output_file, 'r') as f_exp:
            output_lines = f_out.read().rstrip().split('\n')
            expected_lines = f_exp.read().rstrip().split('\n')

            # 删除每行末尾的空格
            output_lines = [line.rstrip() for line in output_lines]
            expected_lines = [line.rstrip() for line in expected_lines]
            if output_lines != expected_lines:
                return '答案错误：你提交的代码没有正确通过样例或运行错误，请检查你的算法是否正确，是否忽略了某些边界情况等等。'

    return '答案正确：你提交的代码运行正常，正确通过了样例（但不代表你的代码能通过最终测试数据）。'


if __name__ == '__main__':
    # 启动Flask应用，并在浏览器中打开
    app_port = 5000
    app_url = f'http://127.0.0.1:{app_port}/'
    app_thread = webbrowser.open_new_tab(app_url)
    app.run(port=app_port)
