"""安全漏洞样本 — 不应通过 Static Gate"""
import os
import subprocess
import pickle
import yaml


# 应被 SEC-SQL-FSTRING 捕获
def bad_query(user_id):
    return f"SELECT * FROM users WHERE id = {user_id}"


# 应被 SEC-CMD-INJECT-FSTRING 捕获
def bad_command(filename):
    os.system(f"rm -rf {filename}")


# 应被 SEC-CMD-INJECT-SUBPROCESS 捕获
def bad_subprocess(cmd):
    subprocess.run(f"echo {cmd}", shell=True)


# 应被 SEC-DESERIALIZE-PICKLE 捕获
def bad_pickle(data):
    return pickle.loads(data)


# 应被 SEC-DESERIALIZE-YAML 捕获
def bad_yaml(data):
    return yaml.load(data)  # 不是 yaml.safe_load


# 应被 SEC-HARDCODED-KEY 捕获
def bad_config():
    return {"api_key": "sk-1234567890abcdef"}


# 应被 SEC-BARE-EXCEPT 捕获
def bad_except():
    try:
        risky_operation()
    except:
        pass


# 应被 SEC-DANGEROUS-BUILTIN 捕获
def bad_eval(expr):
    return eval(expr)


def risky_operation():
    pass
