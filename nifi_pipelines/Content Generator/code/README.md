# Python Environment Setup

This guide explains how to create a Python virtual environment and install project dependencies using `pip` on Linux.

## Prerequisites

* Python 3 installed on your system
* `python3-venv` and `pip` installed (for Debian/Ubuntu)

## Steps

### 1. Check Python Installation

```bash
python3 --version
```

If Python is not installed, install it using:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

---

### 2. Create a Virtual Environment

```bash
python3 -m venv venv
```

This will create a directory named `venv/` containing the virtual environment.

---

### 3. Activate the Virtual Environment (Linux/macOS)

```bash
source venv/bin/activate
```

After activation, your prompt will change to show the environment is active:

```
(venv) $
```

---

### 4. Install Required Packages

Run the following command to install all required packages:

```bash
pip install aiohappyeyeballs==2.6.1 aiohttp==3.11.18 aiosignal==1.3.2 annotated-types==0.7.0 anyio==4.9.0 async-timeout==4.0.3 attrs==25.3.0 certifi==2025.4.26 cffi==1.17.1 charset-normalizer==3.4.2 cryptography==45.0.2 dataclasses-json==0.6.7 distro==1.9.0 exceptiongroup==1.2.2 frozenlist==1.6.0 greenlet==3.2.1 h11==0.16.0 httpcore==1.0.9 httpx==0.28.1 httpx-sse==0.4.0 idna==3.10 jiter==0.9.0 jsonpatch==1.33 jsonpointer==3.0.0 langchain==0.3.25 langchain-community==0.3.23 langchain-core==0.3.58 langchain-text-splitters==0.3.8 langsmith==0.3.42 lxml==5.4.0 marshmallow==3.26.1 multidict==6.4.3 mypy_extensions==1.1.0 numpy==2.2.5 openai==1.77.0 orjson==3.10.18 packaging==24.2 propcache==0.3.1 pycparser==2.22 pydantic==2.11.4 pydantic-settings==2.9.1 pydantic_core==2.33.2 pyspnego==0.11.2 python-dotenv==1.1.0 PyYAML==6.0.2 requests==2.32.3 requests-toolbelt==1.0.0 requests_ntlm==1.3.0 SharePlum==0.5.1 sniffio==1.3.1 SQLAlchemy==2.0.40 tenacity==9.1.2 tqdm==4.67.1 typing-inspect==0.9.0 typing-inspection==0.4.0 typing_extensions==4.13.2 urllib3==2.4.0 yarl==1.20.0 zstandard==0.23.0
```

---

### 5. Verify Installed Packages

```bash
pip list
```

---

### 6. Deactivate the Environment

Once you're done working:

```bash
deactivate
```

---

## Notes

* To delete the environment:

  ```bash
  rm -rf venv
  ```

---

## License

This project setup guide is free to use and share.