import sys

from safeprompt.adapters.uer import load_local


recognizer = load_local(sys.argv[1])
assert recognizer.recognize("张三在北京大学工作。")
print("ok")
