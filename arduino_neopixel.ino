/**
 * Pro3Dscan NeoPixel Controller firmware
 * 
 * This firmware listens on the Serial port for commands from the host computer
 * to dynamically change the lighting conditions of a NeoPixel ring or strip.
 * This is useful for multi-spectral or multi-directional lighting scans.
 * 
 * Commands (Ended with '\n'):
 *   1. All LEDs solid color:   A,R,G,B
 *      Example: A,255,0,0      (Set all pixels to red)
 * 
 *   2. Single LED color:       P,Index,R,G,B
 *      Example: P,3,0,255,0    (Set 4th pixel to green)
 * 
 *   3. Brightness:             B,Value
 *      Example: B,128          (Set overall brightness to 50%)
 * 
 *   4. Show Preset Scene:      S,SceneIndex
 *      Example: S,1            (Run rainbow animation)
 * 
 * Dependencies:
 *   - Adafruit NeoPixel Library (Install via Arduino Library Manager)
 */

#include <Adafruit_NeoPixel.h>

#define NEOPIXEL_PIN     6      // Pin connected to the NeoPixel strip DI
#define NUM_PIXELS      16      // Number of NeoPixels in your strip/ring

Adafruit_NeoPixel pixels(NUM_PIXELS, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);
  pixels.begin();
  pixels.setBrightness(100); // Default middle-ground brightness
  
  // Flash green to show initialization success
  colorWipe(pixels.Color(0, 100, 0), 20);
  delay(200);
  colorWipe(pixels.Color(0, 0, 0), 10);
  
  Serial.println("PRO3DSCAN_LIGHT_READY");
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    
    if (cmd.length() == 0) return;
    
    char type = cmd.charAt(0);
    
    // 1. Set All Pixels
    if (type == 'A') {
      // Command format: A,R,G,B
      int firstComma = cmd.indexOf(',');
      int secondComma = cmd.indexOf(',', firstComma + 1);
      int thirdComma = cmd.indexOf(',', secondComma + 1);
      
      if (firstComma != -1 && secondComma != -1 && thirdComma != -1) {
        int r = cmd.substring(firstComma + 1, secondComma).toInt();
        int g = cmd.substring(secondComma + 1, thirdComma).toInt();
        int b = cmd.substring(thirdComma + 1).toInt();
        
        for (int i = 0; i < NUM_PIXELS; i++) {
          pixels.setPixelColor(i, pixels.Color(r, g, b));
        }
        pixels.show();
      }
    }
    // 2. Set Single Pixel
    else if (type == 'P') {
      // Command format: P,Index,R,G,B
      int firstComma = cmd.indexOf(',');
      int secondComma = cmd.indexOf(',', firstComma + 1);
      int thirdComma = cmd.indexOf(',', secondComma + 1);
      int fourthComma = cmd.indexOf(',', thirdComma + 1);
      
      if (firstComma != -1 && secondComma != -1 && thirdComma != -1 && fourthComma != -1) {
        int idx = cmd.substring(firstComma + 1, secondComma).toInt();
        int r = cmd.substring(secondComma + 1, thirdComma).toInt();
        int g = cmd.substring(thirdComma + 1, fourthComma).toInt();
        int b = cmd.substring(fourthComma + 1).toInt();
        
        if (idx >= 0 && idx < NUM_PIXELS) {
          pixels.setPixelColor(idx, pixels.Color(r, g, b));
          pixels.show();
        }
      }
    }
    // 3. Set Brightness
    else if (type == 'B') {
      // Command format: B,Brightness
      int comma = cmd.indexOf(',');
      if (comma != -1) {
        int brightness = cmd.substring(comma + 1).toInt();
        pixels.setBrightness(constrain(brightness, 0, 255));
        pixels.show();
      }
    }
    // 4. Trigger Show Preset
    else if (type == 'S') {
      // Command format: S,SceneIndex
      int comma = cmd.indexOf(',');
      if (comma != -1) {
        int scene = cmd.substring(comma + 1).toInt();
        runScene(scene);
      }
    }
  }
}

// Solid color wipe animation helper
void colorWipe(uint32_t color, int wait) {
  for(int i=0; i<pixels.numPixels(); i++) {
    pixels.setPixelColor(i, color);
    pixels.show();
    delay(wait);
  }
}

// Predefined lighting patterns
void runScene(int scene) {
  switch (scene) {
    case 0: // All Off
      pixels.clear();
      pixels.show();
      break;
      
    case 1: // RGB Cycle Sweep
      for(int r=0; r<3; r++) {
        uint32_t col = (r == 0) ? pixels.Color(150, 0, 0) : 
                      ((r == 1) ? pixels.Color(0, 150, 0) : pixels.Color(0, 0, 150));
        colorWipe(col, 30);
      }
      pixels.clear();
      pixels.show();
      break;

    case 2: // White Ring Sweep (rotates a bright light for shadow casting)
      for (int cycle = 0; cycle < 3; cycle++) {
        for (int i = 0; i < NUM_PIXELS; i++) {
          pixels.clear();
          pixels.setPixelColor(i, pixels.Color(255, 255, 255));
          // Light up adjacent neighbors for a softer spot
          pixels.setPixelColor((i + 1) % NUM_PIXELS, pixels.Color(80, 80, 80));
          pixels.setPixelColor((i - 1 + NUM_PIXELS) % NUM_PIXELS, pixels.Color(80, 80, 80));
          pixels.show();
          delay(100);
        }
      }
      pixels.clear();
      pixels.show();
      break;

    default:
      break;
  }
}
