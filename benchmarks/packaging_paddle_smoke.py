import sys

from safeprompt.adapters.paddle import load_taskflow_local, load_uie_local


loader = load_uie_local if sys.argv[1] == "uie" else load_taskflow_local
recognizer = loader(sys.argv[2])
assert recognizer.recognize("张三在北京大学工作。")
print("ok")
