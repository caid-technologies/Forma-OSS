-- Reusable component library copied from blueprint.db.

with seed (
  id,
  part_number,
  name,
  category,
  description,
  price,
  sourcing_url,
  pins,
  use_cases
) as (
  values
    (
      1,
      'ESP32-WROOM-32D',
      'ESP32 NodeMCU Development Board',
      'Microcontroller',
      'Powerful WiFi + Bluetooth MCU, perfect for IoT, smart home, and cloud-connected automation.',
      4.50,
      'https://www.espressif.com/en/products/modules/esp32',
      $pins$[{"pin_id": "3V3", "name": "3.3V Power Out", "pin_type": "Power", "voltage": 3.3, "description": "3.3V Regulated Output"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "System Ground Reference"}, {"pin_id": "EN", "name": "Enable / Reset", "pin_type": "Passive", "voltage": 3.3, "description": "Reset pin, active low"}, {"pin_id": "VP", "name": "GPIO36 / ADC_CH0", "pin_type": "Analog", "voltage": 3.3, "description": "ADC Input Only"}, {"pin_id": "VN", "name": "GPIO39 / ADC_CH3", "pin_type": "Analog", "voltage": 3.3, "description": "ADC Input Only"}, {"pin_id": "D34", "name": "GPIO34 / ADC_CH6", "pin_type": "Analog", "voltage": 3.3, "description": "Input Only"}, {"pin_id": "D35", "name": "GPIO35 / ADC_CH7", "pin_type": "Analog", "voltage": 3.3, "description": "Input Only"}, {"pin_id": "D32", "name": "GPIO32 / ADC_CH4", "pin_type": "Digital", "voltage": 3.3, "description": "General GPIO"}, {"pin_id": "D33", "name": "GPIO33 / ADC_CH5", "pin_type": "Digital", "voltage": 3.3, "description": "General GPIO"}, {"pin_id": "D25", "name": "GPIO25 / DAC_CH1", "pin_type": "Digital", "voltage": 3.3, "description": "DAC / General GPIO"}, {"pin_id": "D26", "name": "GPIO26 / DAC_CH2", "pin_type": "Digital", "voltage": 3.3, "description": "DAC / General GPIO"}, {"pin_id": "D27", "name": "GPIO27 / ADC_CH17", "pin_type": "Digital", "voltage": 3.3, "description": "General GPIO"}, {"pin_id": "D14", "name": "GPIO14 / SPI_CLK", "pin_type": "SPI", "voltage": 3.3, "description": "SPI Clock"}, {"pin_id": "D12", "name": "GPIO12 / SPI_MISO", "pin_type": "SPI", "voltage": 3.3, "description": "SPI MISO"}, {"pin_id": "D13", "name": "GPIO13 / SPI_MOSI", "pin_type": "SPI", "voltage": 3.3, "description": "SPI MOSI"}, {"pin_id": "D23", "name": "GPIO23 / MOSI", "pin_type": "SPI", "voltage": 3.3, "description": "Primary SPI MOSI"}, {"pin_id": "D22", "name": "GPIO22 / I2C_SCL", "pin_type": "I2C", "voltage": 3.3, "description": "Primary I2C SCL"}, {"pin_id": "D21", "name": "GPIO21 / I2C_SDA", "pin_type": "I2C", "voltage": 3.3, "description": "Primary I2C SDA"}, {"pin_id": "TXD", "name": "GPIO1 / UART_TX", "pin_type": "UART", "voltage": 3.3, "description": "Serial Transmit"}, {"pin_id": "RXD", "name": "GPIO3 / UART_RX", "pin_type": "UART", "voltage": 3.3, "description": "Serial Receive"}, {"pin_id": "D19", "name": "GPIO19 / MISO", "pin_type": "SPI", "voltage": 3.3, "description": "Primary SPI MISO"}, {"pin_id": "D18", "name": "GPIO18 / SCK", "pin_type": "SPI", "voltage": 3.3, "description": "Primary SPI Clock"}, {"pin_id": "D5", "name": "GPIO5 / SS", "pin_type": "SPI", "voltage": 3.3, "description": "Primary SPI Chip Select"}, {"pin_id": "VIN", "name": "External Power In", "pin_type": "Power", "voltage": 5.0, "description": "5V Unregulated Input"}]$pins$::jsonb,
      $use_cases$["iot", "wifi", "bluetooth", "smart-home", "robotics", "automation", "controller", "mcu"]$use_cases$::jsonb
    ),
    (
      2,
      'Arduino-Nano-V3',
      'Arduino Nano v3.0',
      'Microcontroller',
      'Compact ATmega328P microcontroller board. Ideal for lightweight, non-wireless, breadboard-friendly physical computing.',
      3.20,
      'https://store.arduino.cc/products/arduino-nano',
      $pins$[{"pin_id": "5V", "name": "5V Power Out", "pin_type": "Power", "voltage": 5.0, "description": "5V Regulated Power Output"}, {"pin_id": "3V3", "name": "3.3V Power Out", "pin_type": "Power", "voltage": 3.3, "description": "3.3V Regulated Power Output"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "System Ground"}, {"pin_id": "VIN", "name": "Voltage Input", "pin_type": "Power", "voltage": 12.0, "description": "7V-12V Input (regulated down to 5V)"}, {"pin_id": "A0", "name": "Analog 0", "pin_type": "Analog", "voltage": 5.0, "description": "Analog Input 0"}, {"pin_id": "A1", "name": "Analog 1", "pin_type": "Analog", "voltage": 5.0, "description": "Analog Input 1"}, {"pin_id": "A2", "name": "Analog 2", "pin_type": "Analog", "voltage": 5.0, "description": "Analog Input 2"}, {"pin_id": "A3", "name": "Analog 3", "pin_type": "Analog", "voltage": 5.0, "description": "Analog Input 3"}, {"pin_id": "A4", "name": "Analog 4 / I2C_SDA", "pin_type": "I2C", "voltage": 5.0, "description": "I2C SDA / Analog Input 4"}, {"pin_id": "A5", "name": "Analog 5 / I2C_SCL", "pin_type": "I2C", "voltage": 5.0, "description": "I2C SCL / Analog Input 5"}, {"pin_id": "D2", "name": "Digital 2 / INT0", "pin_type": "Digital", "voltage": 5.0, "description": "GPIO / Interrupt 0"}, {"pin_id": "D3", "name": "Digital 3 / PWM", "pin_type": "PWM", "voltage": 5.0, "description": "GPIO / PWM / Interrupt 1"}, {"pin_id": "D4", "name": "Digital 4", "pin_type": "Digital", "voltage": 5.0, "description": "GPIO"}, {"pin_id": "D5", "name": "Digital 5 / PWM", "pin_type": "PWM", "voltage": 5.0, "description": "GPIO / PWM"}, {"pin_id": "D6", "name": "Digital 6 / PWM", "pin_type": "PWM", "voltage": 5.0, "description": "GPIO / PWM"}, {"pin_id": "D7", "name": "Digital 7", "pin_type": "Digital", "voltage": 5.0, "description": "GPIO"}, {"pin_id": "D8", "name": "Digital 8", "pin_type": "Digital", "voltage": 5.0, "description": "GPIO"}, {"pin_id": "D9", "name": "Digital 9 / PWM", "pin_type": "PWM", "voltage": 5.0, "description": "GPIO / PWM"}, {"pin_id": "D10", "name": "Digital 10 / SPI_SS", "pin_type": "SPI", "voltage": 5.0, "description": "SPI SS / PWM"}, {"pin_id": "D11", "name": "Digital 11 / SPI_MOSI", "pin_type": "SPI", "voltage": 5.0, "description": "SPI MOSI / PWM"}, {"pin_id": "D12", "name": "Digital 12 / SPI_MISO", "pin_type": "SPI", "voltage": 5.0, "description": "SPI MISO"}, {"pin_id": "D13", "name": "Digital 13 / Built-in LED", "pin_type": "Digital", "voltage": 5.0, "description": "SPI Clock / Built-in LED"}]$pins$::jsonb,
      $use_cases$["robotics", "learning", "prototyping", "mcu", "basic-electronics", "wearable"]$use_cases$::jsonb
    ),
    (
      3,
      'DHT22',
      'DHT22 Temperature & Humidity Sensor',
      'Sensor',
      'High-accuracy digital relative temperature and humidity sensor module with single-bus interface.',
      2.80,
      'https://www.sparkfun.com/datasheets/Sensors/Temperature/DHT22.pdf',
      $pins$[{"pin_id": "VCC", "name": "VCC Power", "pin_type": "Power", "voltage": 3.3, "description": "Supports 3.3V to 5.0V Supply"}, {"pin_id": "DATA", "name": "Signal Out", "pin_type": "Digital", "voltage": 3.3, "description": "Single-wire digital data out (requires pullup)"}, {"pin_id": "NC", "name": "No Connection", "pin_type": "Passive", "voltage": 0.0, "description": "Do not connect"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Power ground reference"}]$pins$::jsonb,
      $use_cases$["weather-station", "environmental-monitor", "temperature", "humidity", "smart-home", "gardening"]$use_cases$::jsonb
    ),
    (
      4,
      'HC-SR04',
      'Ultrasonic Distance Sensor HC-SR04',
      'Sensor',
      'Ultrasonic rangefinder measuring distance from 2cm to 400cm. Operates primarily at 5V.',
      1.50,
      'https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf',
      $pins$[{"pin_id": "VCC", "name": "5V Power Supply", "pin_type": "Power", "voltage": 5.0, "description": "Requires exactly 5.0V nominal"}, {"pin_id": "TRIG", "name": "Trigger Input", "pin_type": "Digital", "voltage": 5.0, "description": "10us pulse triggers measurement"}, {"pin_id": "ECHO", "name": "Echo Output", "pin_type": "Digital", "voltage": 5.0, "description": "Pulse width matches roundtrip time"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Ground"}]$pins$::jsonb,
      $use_cases$["robotics", "obstacle-avoidance", "distance-sensing", "fluid-level", "security"]$use_cases$::jsonb
    ),
    (
      5,
      'BMP280',
      'BMP280 Barometric Pressure & Temp Sensor',
      'Sensor',
      'High-precision digital altimeter/pressure sensor with I2C and SPI interfaces. Operates at 3.3V.',
      1.80,
      'https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp280/',
      $pins$[{"pin_id": "VCC", "name": "Power VCC", "pin_type": "Power", "voltage": 3.3, "description": "1.8V to 3.6V Supply Input"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Ground"}, {"pin_id": "SCL", "name": "I2C SCL / SPI SCK", "pin_type": "I2C", "voltage": 3.3, "description": "Clock Pin"}, {"pin_id": "SDA", "name": "I2C SDA / SPI MOSI", "pin_type": "I2C", "voltage": 3.3, "description": "Data Input/Output Pin"}, {"pin_id": "CSB", "name": "Chip Select (SPI)", "pin_type": "SPI", "voltage": 3.3, "description": "SPI CSB, active low (pull high for I2C)"}, {"pin_id": "SDO", "name": "SPI MISO / I2C Address Select", "pin_type": "Digital", "voltage": 3.3, "description": "Address LSB / MISO"}]$pins$::jsonb,
      $use_cases$["barometer", "weather-station", "altimeter", "drones", "smart-watch"]$use_cases$::jsonb
    ),
    (
      6,
      'MPU6050',
      'MPU-6050 6-Axis Accelerometer & Gyroscope',
      'Sensor',
      'Inertial Measurement Unit (IMU) combining 3-axis accelerometer, 3-axis gyro, and internal digital motion processor.',
      2.20,
      'https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/',
      $pins$[{"pin_id": "VCC", "name": "VCC Power (3.3V or 5V)", "pin_type": "Power", "voltage": 3.3, "description": "Includes onboard regulator"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Ground"}, {"pin_id": "SCL", "name": "I2C Serial Clock", "pin_type": "I2C", "voltage": 3.3, "description": "I2C SCL Line"}, {"pin_id": "SDA", "name": "I2C Serial Data", "pin_type": "I2C", "voltage": 3.3, "description": "I2C SDA Line"}, {"pin_id": "XDA", "name": "Aux I2C Data", "pin_type": "I2C", "voltage": 3.3, "description": "For connecting external compass"}, {"pin_id": "XCL", "name": "Aux I2C Clock", "pin_type": "I2C", "voltage": 3.3, "description": "For connecting external compass"}, {"pin_id": "AD0", "name": "I2C Address Select", "pin_type": "Digital", "voltage": 3.3, "description": "LSB of I2C address (low=0x68, high=0x69)"}, {"pin_id": "INT", "name": "Interrupt Out", "pin_type": "Digital", "voltage": 3.3, "description": "Motion interrupt output pin"}]$pins$::jsonb,
      $use_cases$["robotics", "balancing-robot", "vr-headset", "drone-stability", "gesture-control", "motion-tracking"]$use_cases$::jsonb
    ),
    (
      7,
      'SG90-Servo',
      'SG90 Micro Servo Motor',
      'Actuator',
      'High-torque lightweight 180-degree micro servo. Excellent for robotic joints, steering, and physical actuators.',
      2.00,
      'http://www.ee.ic.ac.uk/pjs99/ece3/parts/SG90Servo.pdf',
      $pins$[{"pin_id": "5V", "name": "Power VCC (Red)", "pin_type": "Power", "voltage": 5.0, "description": "5.0V nominal power input"}, {"pin_id": "GND", "name": "Ground (Brown)", "pin_type": "Ground", "voltage": 0.0, "description": "Power ground reference"}, {"pin_id": "PWM", "name": "Control Signal (Orange)", "pin_type": "PWM", "voltage": 5.0, "description": "PWM pulse 50Hz, 1ms to 2ms width"}]$pins$::jsonb,
      $use_cases$["robotics", "robotic-arm", "rc-car", "smart-door-lock", "hobbies"]$use_cases$::jsonb
    ),
    (
      8,
      'Relay-5V-1Ch',
      '5V 1-Channel Optocoupled Relay Module',
      'Actuator',
      'Safely switches high-voltage AC or DC appliances using low-voltage logic from MCUs. Actuated by active-low or active-high logic.',
      1.20,
      'https://components101.com/switches/5v-single-channel-relay-module-pinout-features-datasheet',
      $pins$[{"pin_id": "VCC", "name": "Module Power (5V)", "pin_type": "Power", "voltage": 5.0, "description": "5V Relay coil power"}, {"pin_id": "GND", "name": "Module Ground", "pin_type": "Ground", "voltage": 0.0, "description": "System Ground"}, {"pin_id": "IN", "name": "Signal Input", "pin_type": "Digital", "voltage": 5.0, "description": "Logic input to trigger coil (optocoupled)"}, {"pin_id": "COM", "name": "Switch Common Terminal", "pin_type": "Passive", "voltage": 250.0, "description": "High-power common pole"}, {"pin_id": "NO", "name": "Switch Normally Open Terminal", "pin_type": "Passive", "voltage": 250.0, "description": "Connected to COM only when energized"}, {"pin_id": "NC", "name": "Switch Normally Closed Terminal", "pin_type": "Passive", "voltage": 250.0, "description": "Connected to COM by default"}]$pins$::jsonb,
      $use_cases$["home-automation", "smart-plug", "ac-switching", "motor-control", "valve-control"]$use_cases$::jsonb
    ),
    (
      9,
      'SSD1306-I2C',
      '0.96 inch OLED Display (I2C)',
      'Display',
      '128x64 pixels resolution organic LED display. Sharp, contrasty display controlled over simple I2C.',
      2.50,
      'https://components101.com/displays/096-inch-oled-display-module-pinout-datasheet',
      $pins$[{"pin_id": "VCC", "name": "Power VCC", "pin_type": "Power", "voltage": 3.3, "description": "Supports 3.3V or 5V Power Input"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Ground Reference"}, {"pin_id": "SCL", "name": "I2C Serial Clock", "pin_type": "I2C", "voltage": 3.3, "description": "I2C SCL"}, {"pin_id": "SDA", "name": "I2C Serial Data", "pin_type": "I2C", "voltage": 3.3, "description": "I2C SDA"}]$pins$::jsonb,
      $use_cases$["user-interface", "smart-thermostat", "clock", "dashboard", "smart-home"]$use_cases$::jsonb
    ),
    (
      10,
      'Battery-LiPo-3.7V',
      '3.7V Lithium Polymer Battery (1200mAh)',
      'Power',
      'Rechargeable, high-density LiPo power pack. Essential for wearable and off-grid wireless hardware setups.',
      5.50,
      'https://components101.com/batteries/37v-lipo-battery-specification-datasheet',
      $pins$[{"pin_id": "POS", "name": "Positive Lead (Red)", "pin_type": "Power", "voltage": 3.7, "description": "Positive terminal"}, {"pin_id": "NEG", "name": "Negative Lead (Black)", "pin_type": "Ground", "voltage": 0.0, "description": "Negative reference terminal"}]$pins$::jsonb,
      $use_cases$["portable-power", "wearables", "iot-nodes", "drones", "off-grid"]$use_cases$::jsonb
    ),
    (
      11,
      'USB-5V-Plug',
      '5V USB Wall Power Supply',
      'Power',
      'Plugs into any 5V 1A or 2A USB wall block, outputting safe 5V power reference over micro-USB/Type-C or pin leads.',
      1.50,
      'https://en.wikipedia.org/wiki/USB',
      $pins$[{"pin_id": "5V", "name": "5V Power Line", "pin_type": "Power", "voltage": 5.0, "description": "5.0V Regulated Rail"}, {"pin_id": "GND", "name": "Ground", "pin_type": "Ground", "voltage": 0.0, "description": "Ground"}]$pins$::jsonb,
      $use_cases$["stationary-power", "smart-home-hub", "sensors", "relay-controller"]$use_cases$::jsonb
    ),
    (
      12,
      'LED-Red-Generic',
      'Standard Red LED (5mm)',
      'Passives',
      'Standard 5mm red light emitting diode. Useful for simple indicator signals. Needs current-limiting resistor.',
      0.10,
      'https://components101.com/diodes/5mm-red-led-pinout-specifications',
      $pins$[{"pin_id": "ANODE", "name": "Anode (+) Long Lead", "pin_type": "Passive", "voltage": 2.0, "description": "Positive terminal (needs 1.8V - 2.2V forward drop)"}, {"pin_id": "CATHODE", "name": "Cathode (-) Flat Lead", "pin_type": "Ground", "voltage": 0.0, "description": "Ground Reference Pin"}]$pins$::jsonb,
      $use_cases$["status-indicator", "debugging", "blinky", "diagnostics"]$use_cases$::jsonb
    ),
    (
      13,
      'Resistor-220R',
      '220 Ohm Carbon Film Resistor (1/4W)',
      'Passives',
      'Ideal size for current-limiting standard LEDs driven from 5V or 3.3V microcontroller pins.',
      0.05,
      'https://components101.com/resistors/resistor-color-code',
      $pins$[{"pin_id": "1", "name": "Lead 1", "pin_type": "Passive", "voltage": null, "description": "Bidirectional passive pin"}, {"pin_id": "2", "name": "Lead 2", "pin_type": "Passive", "voltage": null, "description": "Bidirectional passive pin"}]$pins$::jsonb,
      $use_cases$["current-limiting", "led-protection", "basic-circuit"]$use_cases$::jsonb
    ),
    (
      14,
      'Resistor-10k',
      '10k Ohm Metal Film Resistor (1/4W)',
      'Passives',
      'Standard resistance for pull-up and pull-down resistor applications, keeping floating lines tied to clean VCC/GND.',
      0.05,
      'https://components101.com/resistors/resistor-color-code',
      $pins$[{"pin_id": "1", "name": "Lead 1", "pin_type": "Passive", "voltage": null, "description": "Bidirectional passive pin"}, {"pin_id": "2", "name": "Lead 2", "pin_type": "Passive", "voltage": null, "description": "Bidirectional passive pin"}]$pins$::jsonb,
      $use_cases$["pull-up", "pull-down", "button-debouncing", "reset-line"]$use_cases$::jsonb
    )
)
insert into public.component_templates (
  id,
  part_number,
  name,
  category,
  description,
  price,
  sourcing_url,
  pins,
  use_cases
)
select
  id,
  part_number,
  name,
  category,
  description,
  price,
  sourcing_url,
  pins,
  use_cases
from seed
on conflict (part_number) do update set
  name = excluded.name,
  category = excluded.category,
  description = excluded.description,
  price = excluded.price,
  sourcing_url = excluded.sourcing_url,
  pins = excluded.pins,
  use_cases = excluded.use_cases;

select setval(
  pg_get_serial_sequence('public.component_templates', 'id'),
  coalesce((select max(id) from public.component_templates), 1),
  true
);
