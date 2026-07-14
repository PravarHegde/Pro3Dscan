import serial
import serial.tools.list_ports
import time

class NeoPixelController:
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.is_connected = False
        
        if port:
            self.connect(port)

    def get_available_ports(self):
        """Scans the system for serial ports and returns list of paths."""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port=None):
        if port:
            self.port = port
            
        if not self.port:
            print("[NeoPixel] No port specified. Running in Mock Mode.")
            return False
            
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            # Wait for Arduino to reset/reboot on connection
            time.sleep(2)
            self.is_connected = True
            print(f"[NeoPixel] Connected successfully on port {self.port} at {self.baudrate} baud.")
            return True
        except Exception as e:
            print(f"[NeoPixel] Failed to connect on port {self.port}: {e}. Running in Mock Mode.")
            self.is_connected = False
            return False

    def disconnect(self):
        if self.ser and self.ser.is_opened:
            self.ser.close()
        self.ser = None
        self.is_connected = False
        print("[NeoPixel] Disconnected serial link.")

    def send_raw_command(self, cmd_str):
        """Sends raw command string over serial if connected, else logs it."""
        if not cmd_str.endswith('\n'):
            cmd_str += '\n'
            
        if self.is_connected and self.ser:
            try:
                self.ser.write(cmd_str.encode('utf-8'))
                self.ser.flush()
                # Debug feedback print
                # print(f"[NeoPixel Send] {cmd_str.strip()}")
                return True
            except Exception as e:
                print(f"[NeoPixel Send Error] Serial communication failed: {e}")
                self.is_connected = False
                return False
        else:
            # Mock log
            print(f"[NeoPixel Mock Output] {cmd_str.strip()}")
            return True

    def set_all(self, r, g, b):
        """Set all NeoPixel LEDs to a specific RGB color."""
        # Protocol: A,R,G,B\n
        # Example: A,255,128,0\n
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return self.send_raw_command(f"A,{r},{g},{b}")

    def set_pixel(self, index, r, g, b):
        """Set a single NeoPixel LED index to a specific RGB color."""
        # Protocol: P,index,R,G,B\n
        # Example: P,5,255,0,0\n
        index = max(0, int(index))
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return self.send_raw_command(f"P,{index},{r},{g},{b}")

    def set_brightness(self, brightness):
        """Set overall brightness multiplier (0 to 255)."""
        # Protocol: B,brightness\n
        # Example: B,128\n
        brightness = max(0, min(255, int(brightness)))
        return self.send_raw_command(f"B,{brightness}")

    def trigger_preset(self, preset_id):
        """Triggers a light show preset on the Arduino."""
        # Protocol: S,preset_id\n
        # Example: S,2\n
        preset_id = max(0, int(preset_id))
        return self.send_raw_command(f"S,{preset_id}")
        
    def trigger_sequence_capture(self, colors):
        """Flashes a list of colors sequentially (for photometric scanning).
        colors: list of tuples/lists [(R, G, B), ...]
        """
        for i, color in enumerate(colors):
            print(f"[Sequence] Flashing color {i}: {color}")
            self.set_all(*color)
            time.sleep(0.5) # Wait for camera to adjust exposure (managed by scan script)
        self.set_all(0, 0, 0) # Turn off
