from pathlib import Path

def temperatures():
    """
    Read temperatures (°C) for various sensors.

    Yields:

        {
            "path": "/sys/class/hwmon/hwmon3",
            "name": "coretemp",
            "device": "/sys/devices/platform/coretemp.0",
            "temperature": 47.0,
            "model": ""
        }
        {
            "path": "/sys/class/hwmon/hwmon1",
            "name": "nvme",
            "device": "/sys/devices/pci0000:00/0000:00:1d.0/0000:3c:00.0/nvme/nvme0",
            "temperature": 32.85,
            "model": "Samsung SSD 970 EVO 250GB"
        }
    """
    for hwmon in Path("/sys/class/hwmon").glob("*"):
        temperature_info = {
            "path": str(hwmon),
            "name": (hwmon / "name").read_text().strip(),
            "device": str((hwmon / "device").resolve()),
            "temperature": -1,
            "model": ""
        }
        try:
            temperature_info["temperature"] = int((hwmon / "temp1_input").read_text()) / 1000
        except OSError:
            pass

        try:
            temperature_info["model"] = (hwmon / "device" / "model").read_text().strip()
        except FileNotFoundError:
            pass

        yield temperature_info
