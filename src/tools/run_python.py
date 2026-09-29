import subprocess
import sys

from src.tools.base import Tool


class RunPythonTool(Tool):
    name = "run_python"
    description = "Chạy một đoạn code Python và trả về kết quả in ra (stdout/stderr)"

    def run(self, code: str) -> str:
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip()
            error = result.stderr.strip()

            if error:
                msg = f"{output}\n\nLỗi:\n{error}" if output else f"Lỗi:\n{error}"
                return {"success": False, "error": msg}

            result = output if output else "(code chạy xong, không có output)"
            return {"success": True, "result": result}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Lỗi: code chạy quá 10 giây (timeout)."}
        except Exception as e:
            return {"success": False, "error": f"Lỗi khi chạy code: {e}"}

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Đoạn code Python cần chạy (dùng print() để in kết quả)",
                    }
                },
                "required": ["code"],
            },
        }