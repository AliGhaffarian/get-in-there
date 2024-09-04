import pathlib
import subprocess
import math
import time
import datetime
import os
import logging
import colorlog
import concurrent.futures
"""
default configs for the loggers in the rafece2
"""

# Define the format and log colors
log_format = '%(asctime)s [%(levelname)s] %(name)s [%(funcName)s]: %(message)s'
log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
        }

# Create the ColoredFormatter object
console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s' + log_format,
        log_colors = log_colors
        )

stdout_handler=logging.StreamHandler()
stdout_handler.setFormatter(console_formatter)
stdout_handler.setLevel(logging.DEBUG)

logger = logging.getLogger()

logger.setLevel(logging.DEBUG)
logger.addHandler(stdout_handler)


REPO="https://github.com/AliGhaffarian/mylinux"
SIZE_THRESHHOLD=1 *  1024 * 1024 * 70
GITHUB_SIZE_LIMIT= 1 * 1024 * 1024 * 100
FILE_NAME=datetime.datetime.fromtimestamp(time.time()).strftime("%d_%m_%Y:%H:%M")
OLD_PWD : pathlib.Path =pathlib.Path().resolve()
MAX_PUSH_ATTEMPTS=5

path_size_cache : dict = {}

def convert_size(size_bytes):
    #https://stackoverflow.com/questions/5194057/better-way-to-convert-file-sizes-in-python
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])


def size_to_byte(size):
    raise NotImplementedError


def size_of_path(path : pathlib.Path):

    try:
        res : int= path_size_cache[path]
        return res

    except KeyError:
        pass

    path=pathlib.Path(path)

    if path.is_file():
        res = path.stat().st_size
        path_size_cache.update({path : res})
        return res

    res = 0

    for subfile in list(path.glob("*")):
        if subfile.is_file():
            res += subfile.stat().st_size
            continue
        res += size_of_path(subfile)

    path_size_cache.update({path : res})
    return res 

def backup_init():
    os.chdir(os.environ['HOME'])
    subprocess.run(["git", "init"])
    subprocess.run(["git", "remote", "add", "origin", REPO])

    subprocess.run(["git", "fetch", "--filter=blob:none", "--depth", "1", "origin"])
    subprocess.run(["git", "add", f"{OLD_PWD}/.gitattributes"])
    subprocess.run(["git", "branch", f"main"])
    subprocess.run(["git", "switch", f"main"])


def push_backup(path : pathlib.Path):

    size=convert_size(size_of_path(path))

    if size_of_path(path) > GITHUB_SIZE_LIMIT:
        logger.critical(f"{path} is bigger than githubs upload limit")
        return 
    logger.info(f"pushing '{path}', size: {size}")
    subprocess.run(["git", "add", str(path)])
    subprocess.run(["git", "commit", "-m", FILE_NAME],\
            stdout=subprocess.DEVNULL,\
            stderr=subprocess.DEVNULL)

    push_success=False
    push_attempts=0

    while push_success == False and push_attempts < MAX_PUSH_ATTEMPTS:
        if push_attempts:
            logger.warning(f"failed to push, attemp {push_attempts} of {MAX_PUSH_ATTEMPTS}")
        push_attempts += 1
        
        p_report=subprocess.run(["git", "push", "-f", "--set-upstream", "origin", "main"])
        if p_report.returncode == 0:
            push_success=True
        push_attempts += 1 

    if push_success == False:
        logger.error(f"failed to push {path}")
        

def push_backup_list(paths : list[pathlib.Path]):
    size = 0
    for path in paths:
        size += size_of_path(path)
    logger.info(f"pushing group {paths}, {convert_size(size)}")

    for path in paths:
        if size_of_path(path) > GITHUB_SIZE_LIMIT:
            logger.critical(f"{path} is bigger than githubs upload limit, skipping")
            continue
 
        subprocess.run(["git", "add", str(path)])
    subprocess.run(["git", "commit", "-m", FILE_NAME],\
            stdout=subprocess.DEVNULL,\
            stderr=subprocess.DEVNULL)


    push_success=False
    push_attempts=0

    while push_success == False and push_attempts < MAX_PUSH_ATTEMPTS:
        if push_attempts:
            logger.warning(f"failed to push, attemp {push_attempts} of {MAX_PUSH_ATTEMPTS}")
        push_attempts += 1
        
        p_report=subprocess.run(["git", "push", "-f", "--set-upstream", "origin", "main"])
        if p_report.returncode == 0:
            push_success=True
        push_attempts += 1 

    if push_success == False:
        logger.error(f"failed to push {paths}")
        




def backup_wrapup():
    subprocess.run(["rm", "-rf", ".git"])
    os.chdir(OLD_PWD)

def optimized_backup_push(dirs : list[pathlib.Path])->int:
    push_list = [dirs[0]]
    current_push_list_size = size_of_path(dirs[0])
    for direc in dirs[1:]:
        if size_of_path(direc) + current_push_list_size < SIZE_THRESHHOLD:
            push_list.append(direc)
            current_push_list_size += size_of_path(direc)
    push_backup_list(push_list)
    return len(push_list)

def backup_dir(path: pathlib.Path):

    path=pathlib.Path(path)

    if pathlib.Path(path).is_file():
        push_backup(path)
        return

    if size_of_path(path) > SIZE_THRESHHOLD:
        children = list(path.glob("*"))

        if len(children) == 0:
            logger.critical(f"{path} doesnt have any children {children=}")
            return
        
        children.sort(key=size_of_path)
        number_of_pushed_childs=0
        if size_of_path(children[0]) < SIZE_THRESHHOLD:
            number_of_pushed_childs=optimized_backup_push(children)
        
        assert number_of_pushed_childs >= 0 and number_of_pushed_childs <= len(children)
        
        for child in children[number_of_pushed_childs:]:
            backup_dir(child)
        return

    push_backup(path)

if __name__ == "__main__":
    targets_files = []

    e = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    target_files_list=open("targets.txt", "r")\
            .read()\
            .strip()\
            .replace("~", os.environ['HOME'])\
            .split("\n")

    target_files_list = [*map(lambda x: x.strip(), target_files_list)]

    backup_init()
    for path in target_files_list:
        targets_files.append(pathlib.Path(path).resolve())

    for target in targets_files:
        backup_dir(pathlib.Path(target))

    backup_wrapup()

