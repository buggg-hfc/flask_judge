import unittest
from app import compile_and_test_cpp
from pathlib import Path


class CompileAndTestCPPTests(unittest.TestCase):
    def setUp(self):
        self.test_files_path = Path('test_files')
        self.assertTrue(self.test_files_path.exists(), "测试文件目录不存在。")

    def test_ac(self):
        # 测试正常代码
        result = compile_and_test_cpp(self.test_files_path / 'test_ac.cpp')
        self.assertIn('答案正确', result)

    def test_wa(self):
        # 测试错误代码
        result = compile_and_test_cpp(self.test_files_path / 'test_wa.cpp')
        self.assertIn('答案错误', result)

    def test_tle(self):
        # 测试超时代码
        result = compile_and_test_cpp(self.test_files_path / 'test_tle.cpp')
        self.assertIn('运行超时', result)

    def test_mle(self):
        # 测试内存溢出
        result = compile_and_test_cpp(self.test_files_path / 'test_mle.cpp')
        self.assertIn('内存超限', result)

    def test_shutdown(self):
        # 测试关机指令
        result = compile_and_test_cpp(self.test_files_path / 'test_shutdown.cpp')
        self.assertIn('拒绝编译', result)

    def test_tle_in_compiling(self):
        # 测试卡编译指令
        result = compile_and_test_cpp(self.test_files_path / 'test_tle_in_compiling.cpp')
        self.assertNotIn('答案正确', result)


if __name__ == '__main__':
    unittest.main()
