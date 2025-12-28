#!/bin/bash

# Değiştirmek istediğiniz ağ arayüzü
INTERFACE="enx4cea4168104d"

# Yeni IP adresi
NEW_IP="10.42.0.2"
NETMASK="255.255.255.0"
GATEWAY="192.168.1.1"

# Eski IP'yi kaldır
sudo ip addr flush dev $INTERFACE

# Yeni IP'yi ekle
sudo ip addr add $NEW_IP/$NETMASK dev $INTERFACE

# Varsayılan gateway'i ayarla
sudo ip route add default via $GATEWAY

# Ağ arayüzünü yeniden başlat
sudo ifconfig $INTERFACE up

echo "IP adresi değiştirildi: $NEW_IP"

