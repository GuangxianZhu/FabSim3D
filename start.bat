@echo off
rem NOTE: every rem line with Chinese text ends in " ." on purpose. cmd.exe on a
rem Chinese (GBK) code page may glue the byte after a Chinese character onto it;
rem the trailing ASCII dot is what gets eaten, never the line break.
rem ============================================================
rem  FabSim3D one-click launcher for Windows
rem  - finds Python 3 (py launcher or python on PATH)
rem  - creates a private virtual env in .venv on first run
rem  - installs / updates requirements.txt when it changes
rem  - starts the app; any arguments are passed to main.py
rem    e.g.  start.bat --lang en      start.bat --lesson 1
rem ============================================================
rem 【中文说明】Windows 一键启动脚本：双击 start.bat 就能运行 FabSim3D。 .
rem  这是一个“批处理文件”（.bat）：里面每一行都是一条 Windows 命令行（cmd）命令，从上往下依次执行。 .
rem  以 rem 开头的行是注释，cmd 会直接跳过，不会显示也不会执行。 .
rem  它依次做这些事： .
rem    1. 如果是用 git 下载的，先自动更新到最新版本； .
rem    2. 找到电脑上的 Python 3； .
rem    3. 第一次运行时，在 .venv 文件夹里建一个本程序专用的 Python 环境（虚拟环境），不影响电脑上其他程序； .
rem    4. 安装或更新需要的第三方库（列在 requirements.txt 里）； .
rem    5. 启动程序 main.py。任何一步出错都会显示英文提示并暂停，方便看清原因。 .
rem
rem  第一行 @echo off：关闭“命令回显”，否则 cmd 会把每条命令本身也打印出来，屏幕会很乱； .
rem  开头的 @ 表示连这一行自己也不回显。 .
rem  setlocal：本脚本里设置的变量只在本脚本内有效，脚本结束后自动清除，不污染系统环境。 .
rem  cd /d "%~dp0"：切换到本脚本所在的文件夹。 %~dp0 是一个特殊写法，表示“本脚本所在的盘符+路径” .
rem  （d = 盘符，p = 路径，0 = 第 0 个参数即脚本自己）；/d 表示连盘符一起切换（比如从 C: 切到 D:）。 .
rem  这样无论从哪里双击运行，后面的相对路径（.venv、main.py 等）都能找对。 .
rem  title：设置命令行窗口的标题。 .
setlocal
cd /d "%~dp0"
title FabSim3D

rem ---------- pull the latest main (only on branch main, fast-forward only) ----------
rem  Set FABSIM3D_NOUPDATE=1 to skip.  The whole update runs inside one ( ) block,
rem  which cmd parses before executing, because git may rewrite this very file;
rem  afterwards the (possibly new) start.bat is re-run from the top.
rem 【中文】第 1 部分：自动更新。 .
rem  只有当本文件夹是 git 仓库（存在 .git 文件夹）、当前在 main 分支上、且没有设置 .
rem  FABSIM3D_NOUPDATE 这个变量时才更新。想跳过更新，可以先在命令行执行 set FABSIM3D_NOUPDATE=1。 .
rem  set "BRANCH="：先把变量 BRANCH 清空。把整个 名字=值 放进引号里，可以避免行尾多余空格被算进值里。 .
rem  if not defined X：如果变量 X 不存在。if exist ".git\"：如果 .git 文件夹存在（末尾的 \ 表示是文件夹）。 .
rem  for /f ... in ('命令') do ...：运行引号里的命令，把它输出的每一行放进 %%B 再执行 do 后面的命令。 .
rem  这里运行的 git rev-parse --abbrev-ref HEAD 会输出当前分支名，于是 BRANCH 就等于分支名。 .
rem  在 .bat 文件里循环变量要写两个百分号 %%B；2^>nul 把错误信息丢掉（^ 是转义符， .
rem  让 > 在括号里的命令中被当作普通字符传进去，而不是被外层当成重定向）。 .
set "BRANCH="
if not defined FABSIM3D_NOUPDATE if exist ".git\" (
    for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
)
rem  下面这个用圆括号 ( ) 包起来的整块：cmd 会先把括号里的所有行一次性读进来，再执行。 .
rem  这很重要：git pull 可能会改写 start.bat 自己，如果 cmd 边读边执行，文件被改后就会读乱。 .
rem  if /i：比较时不区分大小写。 .
rem  git pull --ff-only origin main：从网上拉取最新代码，只允许“快进”式更新（不会自动合并、不会覆盖本地改动）。 .
rem  “命令A || 命令B”：A 失败时才执行 B，这里是更新失败（没网或本地有改动）时显示提示，然后照常启动。 .
rem  echo 行里的 ^( 和 ^) 是转义写法，让括号作为普通文字显示，而不被当成代码块的开始/结束。 .
rem  set "FABSIM3D_NOUPDATE=1"：标记“已经更新过了”，避免下面重新运行时又更新一遍、无限循环。 .
rem  call "%~f0" %*：重新运行本脚本（ %~f0 是本脚本的完整路径， %* 是用户传入的全部参数）， .
rem  这样执行的是更新后的新版 start.bat。exit /b：新版运行完后，退出当前这个旧版脚本。 .
if /i "%BRANCH%"=="main" (
    echo [FabSim3D] Checking for updates on main ...
    git pull --ff-only origin main || echo [FabSim3D] Update skipped ^(offline or local changes^), starting the current version.
    set "FABSIM3D_NOUPDATE=1"
    call "%~f0" %*
    exit /b
)

rem 【中文】第 2 部分：定义几个路径变量，后面用 百分号包住变量名的写法（如 %VPY% ）来引用它们。 .
rem  VENV  虚拟环境所在的文件夹 .venv； .
rem  VPY   虚拟环境里的 python.exe（以后都用它运行，而不是系统的 Python）； .
rem  STAMP 一个“记号文件”：每次装好依赖后，把 requirements.txt 复制一份存成它， .
rem        下次启动时比较两者，就知道依赖列表有没有变、需不需要重新安装。 .
set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\requirements.installed"

rem  如果虚拟环境已经建好了，就直接跳到 :deps 标签处（检查依赖），跳过下面“找 Python、建环境”的步骤。 .
rem  goto :名字 —— 跳到以“:名字”开头的那一行继续执行；以冒号开头的行叫“标签”，只是一个跳转位置。 .
if exist "%VPY%" goto :deps

rem ---------- locate a system Python ----------
rem 【中文】第 3 部分：在电脑上找一个可用的 Python 3（只有第一次运行时才需要）。 .
rem  py 是 Windows 版 Python 自带的“启动器”，py -3.12 表示指定用 3.12 版本。 .
rem  for %%V in (列表) do ...：对列表里每个版本号依次尝试；if not defined PY 表示“还没找到才继续试”。 .
rem  “命令 >nul 2>&1”：把正常输出和错误输出都丢掉，不在屏幕上显示。 .
rem  “命令A && 命令B”：A 成功时才执行 B，即这个版本能运行，就把 PY 设为对应的命令。 .
rem  优先选 panda3d（3D 引擎）提供现成安装包的版本。找到了就跳到 :mkvenv 去建虚拟环境。 .
set "PY="
rem prefer versions that panda3d ships wheels for, then any Python 3
for %%V in (3.12 3.11 3.10 3.13 3.9) do if not defined PY (py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V")
if defined PY goto :mkvenv
rem  上面都没找到：再试 py -3（任意 Python 3），要求版本不低于 3.8。 .
rem  python -c "..." 直接运行引号里的一小段 Python 代码：版本够新就以 0 退出（成功），否则以 1 退出（失败）。 .
rem  errorlevel 是上一条命令的“退出码”：0 通常表示成功，非 0 表示失败。 .
rem  注意 if errorlevel 1 的意思是“退出码大于等于 1”，所以 if not errorlevel 1 就是“退出码为 0，即成功”。 .
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :mkvenv
rem  还没找到：最后试一下 PATH 里的 python 命令。 .
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :mkvenv

rem  到这里说明完全找不到 Python：显示安装提示。 .
rem  echo. 输出一个空行；pause 显示“请按任意键继续”并等待，防止窗口一闪就关掉看不到提示； .
rem  exit /b 1 以退出码 1（表示出错）结束脚本。 .
echo.
echo [FabSim3D] Python 3.8+ was not found.
echo            Please install Python 3 (64-bit) from https://www.python.org/downloads/
echo            and tick "Add python.exe to PATH" in the installer, then run start.bat again.
echo.
pause
exit /b 1

rem 【中文】第 4 部分（标签 :mkvenv）：用找到的 Python 创建虚拟环境。 .
rem  python -m venv 文件夹名 —— 新建一个独立的 Python 环境，以后安装的库都放在里面。 .
rem  如果命令失败，或者建完后找不到 python.exe，就跳到 :fail_venv 显示错误。 .
:mkvenv
echo [FabSim3D] First run: creating virtual environment in %VENV% ...
%PY% -m venv "%VENV%"
if errorlevel 1 goto :fail_venv
if not exist "%VPY%" goto :fail_venv

rem 【中文】第 5 部分（标签 :deps）：检查是否需要安装依赖库。 .
rem  记号文件不存在（从没装过）→ 去 :install 安装。 .
rem  fc /b 文件1 文件2：按字节逐个比较两个文件（fc = file compare，/b = 二进制方式）。 .
rem  两文件完全相同时 errorlevel 为 0；不同（说明 requirements.txt 改过）时为 1 → 去 :install 重新安装。 .
rem  都没问题就直接跳到 :run 启动程序。 .
:deps
rem ---------- install requirements if missing or changed ----------
if not exist "%STAMP%" goto :install
fc /b "requirements.txt" "%STAMP%" >nul 2>&1
if errorlevel 1 goto :install
goto :run

rem 【中文】第 6 部分（标签 :install）：安装依赖库。 .
rem  先悄悄（-q）把 pip（Python 的安装工具）升级到最新版； .
rem  再按 requirements.txt 安装所需的库（panda3d、numpy、matplotlib）。 .
rem  成功就跳到 :installed；失败的话（国内网络常连不上默认的国外服务器）， .
rem  改用清华大学的国内镜像（-i 指定下载地址）再试一次，还失败就跳到 :fail_pip 报错。 .
:install
echo [FabSim3D] Installing dependencies (panda3d, numpy, matplotlib) ...
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip >nul 2>&1
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto :installed
echo [FabSim3D] Default package index failed, retrying with Tsinghua mirror ...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :fail_pip
rem  安装成功：把 requirements.txt 复制一份作为记号文件（/y 表示覆盖时不询问），下次启动就不用重复安装。 .
:installed
copy /y "requirements.txt" "%STAMP%" >nul

rem 【中文】第 7 部分（标签 :run）：用虚拟环境里的 Python 启动程序 main.py，并把用户给的参数 %* 原样传过去。 .
rem  程序正常关闭（退出码 0）就结束脚本；如果程序出错退出，跳到 :fail_run 暂停，让用户看到错误信息。 .
:run
echo [FabSim3D] Starting ...
"%VPY%" main.py %*
if errorlevel 1 goto :fail_run
exit /b 0

rem 【中文】下面三段是出错时的提示：分别对应建虚拟环境失败、安装依赖失败、程序运行出错。 .
rem  每段都显示提示、pause 暂停等用户看完，然后以退出码 1 结束。 .
:fail_venv
echo.
echo [FabSim3D] Could not create the virtual environment in %VENV%.
echo            Delete the %VENV% folder and try again.
pause
exit /b 1

:fail_pip
echo.
echo [FabSim3D] Installing dependencies failed. Check your network connection and run start.bat again.
pause
exit /b 1

:fail_run
echo.
echo [FabSim3D] The program exited with an error (see messages above).
pause
exit /b 1
