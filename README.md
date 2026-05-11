# cow_solver - 桌面自动化辅助工具

**cow_solver** 是一款基于图像识别与自动化控制的桌面辅助工具，专为解决行列放置类益智游戏而设计。游戏规则是每行、每列、每个颜色只能放置一只牛，通过逻辑推理找出唯一解。工具结合了屏幕截图、图像处理和自动点击等功能，实现半自动或全自动的操作体验。

## 功能特性

- 🖼️ **屏幕区域选择与截图捕获**：利用 [mss](https://github.com/BoboTiG/python-mss) 和 [pyautogui](https://github.com/asweigart/pyautogui) 实现精准截图
- 🔍 **图像解析与状态识别**：使用 Pillow 和 NumPy 进行图像分析与处理
- ⚡ **自动化操作执行**：通过 pyautogui 模拟鼠标/键盘操作
- 🌐 **Web 界面控制**：基于 Flask 的本地 Web 控制界面
- 🎛️ **双模式操作**：支持手动和自动两种交互模式
- 🧵 **后台多线程**：独立线程执行自动化任务，不影响界面响应

## 系统要求

- Python 3.7+
- Windows 10/11

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/cow_solver.git
cd cow_solver
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 启动应用

```bash
python run.py
```

这将启动 Flask 服务器并在 PyWebView 窗口中打开控制面板。

### 访问 Web 界面（备用）

如果不想使用 PyWebView 窗口，也可以直接启动 Flask 服务：

```bash
cd server
python app.py
```

然后访问 `http://localhost:5000`

## 项目结构

```
cow_solver/
├── assets/              # 静态资源
├── frontend/            # 前端文件
├── server/              # Flask 后端服务
│   ├── app.py           # Flask 应用创建
│   ├── routes_manual.py # 手动模式路由
│   ├── routes_auto.py   # 自动模式路由
│   ├── auto_thread.py   # 自动化线程管理
│   └── engine/          # 核心引擎
├── solver/              # 图像解析与求解模块
│   ├── solver.py        # 主求解逻辑
│   ├── parser.py        # 图像解析器
│   ├── renderer.py      # 渲染器
│   └── utils.py         # 工具函数
├── requirements.txt     # Python 依赖
├── environment.yml      # Conda 环境配置
├── run.py              # 应用程序主入口
└── README.md
```

## 依赖库

- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [PyWebView](https://pywebview.flowrl.com/) - 桌面窗口框架
- [Pillow](https://pillow.readthedocs.io/) - 图像处理
- [NumPy](https://numpy.org/) - 数组计算
- [mss](https://github.com/BoboTiG/python-mss) - 屏幕截图
- [pyautogui](https://pyautogui.readthedocs.io/) - 自动化控制

## 注意事项

⚠️ **警告**: 此工具包含自动化控制功能（如模拟鼠标点击），请确保遵守相关软件和服务的使用条款，合法合规地使用本工具。

## 贡献

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目！

## 许可证

[MIT License](LICENSE)
