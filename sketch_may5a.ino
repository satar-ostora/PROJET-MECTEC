#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "TON_WIFI";
const char* password = "PASSWORD";
const char* mqtt_server = "192.168.1.X";

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }

  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) {
    while (!client.connect("ESP32_Client")) {
      delay(1000);
    }
  }

  // Exemple de données JSON
  String payload = "{";
  payload += "\"id\":\"casque01\",";
  payload += "\"temp\":36.5,";
  payload += "\"co_ppm\":20,";
  payload += "\"heart_rate\":75,";
  payload += "\"spo2\":97,";
  payload += "\"fall\":false,";
  payload += "\"alert_level\":0";
  payload += "}";

  client.publish("casque/data", payload.c_str());

  delay(2000);
}