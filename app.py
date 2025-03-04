from typing import Optional

import os
import io
import zlib
import time
import json
import zipfile
import requests
import subprocess

from configparser import ConfigParser
from concurrent.futures import ThreadPoolExecutor
from tkinter.filedialog import askdirectory

def crc32(fn, size=65536):
    with open(fn, "rb") as f:
        checksum = 0
        while (chunk := f.read(size)) :
            checksum = zlib.crc32(chunk, checksum)
        return checksum

class Installer:
    URL = "https://patch-cls.naddic.co.kr/closerskr/LIVE"
    CLOSERS_PATH = "test"
    CODE_MIN = 0
    CODE_MAX = 2
    
    def __init__(self, path: Optional = None):
        if path:
            self.CLOSERS_PATH = path
        else:
            self.CLOSERS_PATH = "{}/{}".format(os.path.dirname(os.path.realpath(__file__)), self.CLOSERS_PATH)
        
        self.version = self.get_version()
        self.VERSION_MVER = self.version.get("Ver", "MVer")
        self.VERSION_TIME = self.version.get("Ver", "Time")
        self.logger("선택된 클로저스 설치 경로: {}".format(self.CLOSERS_PATH))
        self.logger("최신 클라이언트 버전: {}".format(self.VERSION_MVER))
        
    def logger(self, *args, **kwargs):
        dt = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{dt}]", *args, **kwargs)
        
    def get_path(self, fn: str):
        return r"{}/{}".format(self.CLOSERS_PATH, fn)
    
    def client_lua_check(self):
        check_list = [ f"CLIENT_CODE_{i}.LUA" for i in range(self.CODE_MIN, self.CODE_MAX + 1) ]
        return all([os.path.exists(self.get_path(f)) for f in check_list])
    
    def client_zip_check(self):
        check_list = [ f"CLIENT_CLOSERS_{i}.zip" for i in range(0, 14) ] # ~16
        return list(filter(lambda f: os.path.exists(self.get_path(f)), check_list))
        
    def unzip_file(self):
        fn = self.client_zip_check()[0]

        try:
            zf = zipfile.ZipFile(self.get_path(fn))
            self.logger(f"압축 파일을 불러오는 중입니다: {fn}")
            
            if zf.testzip() is not None:
                return False
            self.logger(f"압축 파일을 불러왔습니다: {fn}", flush=True)
            s = time.time()
            
            with ThreadPoolExecutor(100) as exe:
                _ = [exe.submit(zf.extract, f, self.get_path("")) for f in zf.namelist()]
            
            e = time.time()
            self.logger(f"압축 해제를 완료했습니다: {fn} ({round((e-s)*1000)}ms)", flush=True)
            
            zf.close()
            os.remove(self.get_path(fn))
        except Exception as err:
            # self.logger("압축 해제 실패:", err)
            return False
    
    def find_launcher(self):
        if os.path.exists(self.get_path("CLOSERS.exe")):
            return self.run_launcher()
            
        if not os.path.exists(self.get_path("LAUNCHER.exe")):
            self.logger("클로저스 런처 파일을 찾을 수 없습니다.")
            return
            
        if not os.path.exists("luadec.exe"):
            self.logger("luadec.exe 파일을 찾을 수 없습니다.")
            return
        
        self.logger("클로저스 실행기 구동을 준비중입니다.")
        self.write_version(True)
        launcher = subprocess.Popen([self.get_path("LAUNCHER.exe"), "_KOR", "naddiclauncherkor:000000000%0000000000-0000-0000-0000-000000000000", "_LC", "1"],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT)
    
        while True:
            if os.path.exists(self.get_path("CLOSERS.exe")):
                subprocess.call("taskkill /IM LAUNCHER.exe")
                subprocess.call("taskkill /IM CLOSERS.exe")
                return self.run_launcher()
            time.sleep(4)
    
    def run_launcher(self):
        self.logger("클로저스 실행기를 구동합니다.")
        self.write_version(True)
        launcher = subprocess.Popen([self.get_path("CLOSERS.exe"), "_KOR", "naddiclauncherkor:000000000%0000000000-0000-0000-0000-000000000000", "_LC", "1"],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT)
            
        while True:
            if launcher.poll() is None:
                if self.client_zip_check():
                    self.unzip_file()
                
                if self.client_lua_check():
                    self.logger("업데이트 목록 파일를 찾았습니다.")
                    time.sleep(3)
                    launcher.kill()
                    self.update_closers()
                    break
            else:
                self.logger(f"패치에 실패했습니다: process exited with code {launcher.poll()}")
                return False
            time.sleep(1)
        return True
        
    def check_files(self, data: list[list]):
        update_list = []
        with ThreadPoolExecutor(max_workers=100) as exe:
            res = list(exe.map(self.check_files_exe, data))
            for i in res:
                if i is not None:
                    update_list.append(i)
        return update_list
                
    def check_files_exe(self, d: list):
        path = f"{d[0]}{d[1]}"
        if not os.path.exists(self.get_path(path)):
            dir_path = os.path.dirname(self.get_path(path))
            try:
                if not os.path.isdir(dir_path):
                    os.makedirs(dir_path)
            except FileExistsError:
                pass
            return [path, "{}/PATCH/PATCH_{}_{}/{}".format(
                self.URL, d[6], d[9], path
            )]
        else:
            if crc32(self.get_path(path)) != d[2]:
                return [path, "{}/PATCH/PATCH_{}_{}/{}".format(
                    self.URL, d[6], d[9], path
                )]
        return None
            
    def update_closers(self):
        update_list = []
        threads = {}
        
        self.logger(f"파일 검사 및 업데이트 파일 탐색을 시작합니다.")
        for i in range(self.CODE_MIN, self.CODE_MAX + 1):
            data = self.read_update_list(i)
            update_list += self.check_files(data)
            self.logger(f"{i + 1}번 파일 검사가 완료되었습니다. ({i + 1}/{self.CODE_MAX + 1})")
            
        self.logger(f"업데이트 파일 {len(update_list)}개를 찾았습니다.")
        time.sleep(2)

        with ThreadPoolExecutor(max_workers=100) as exe:
            _ = list(exe.map(self.download_file, update_list))
            
        self.write_version()
        self.logger("클로저스 설치가 완료되었습니다.")
        
    def download_file(self, data: list):
        res = requests.get(data[1])
        if res.status_code == 200:
            with open(self.get_path(data[0]), "wb") as f:
                f.write(res.content)
            self.logger(f"다운로드: {data[0]}")
        
    def get_version(self) -> ConfigParser:
        version = ConfigParser()
        version.read_file(io.StringIO(
            requests.get("{}/VER.DLL".format(self.URL)).text
        ))
        return version
        
    def get_update_list(self, idx: int):
        patch_list = requests.get("{}/PATCH/PATCH_{}_{}/CLIENT_CODE_{}.LUA".format(
            self.URL, self.VERSION_MVER, self.VERSION_TIME, idx
        ))
        with open("CLIENT_CODE_{}.LUA".format(idx), "wb") as f:
            f.write(patch_list.content)

    def read_update_list(self, idx: int) -> list[list]:
        out = subprocess.Popen(["luadec", self.get_path(f"CLIENT_CODE_{idx}.LUA")],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT)

        stdout, stderr = out.communicate()
        
        if not stdout is None:
            data = stdout.decode("utf-8")
            data = data[data.find("CODE_TABLE = {") + 13 : data.rfind("DELETE_CODE_TABLE")]
            data = data.replace("{", "[").replace("}", "]")
            return json.loads(data)
        return []

    def write_version(self, fake = False):
        f = open(self.get_path("VER.DLL"), "w")
        if fake:
            f.write("[Ver]\nMVer=0\nTime=0\nCrc=0")
        else:
            f.write(f"[Ver]\nMVer={self.VERSION_MVER}\nTime={self.VERSION_TIME}\nCrc=0\nPATCH=1")
        f.close()

if __name__ == "__main__":
    i = Installer(askdirectory())
    i.find_launcher()
    os.system("pause")
