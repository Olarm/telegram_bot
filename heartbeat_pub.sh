#!/bin/bash

timestamp() {
  date +"%T" # current time
}

[ "$#" -eq 1 ] || die "broker ip required, $# provided"

broker=$1

if mosquitto_pub -h $broker -t heartbeat/$HOSTNAME -m 1 2> /dev/null ; then
    echo "1"
else
    echo "0"
    ts=`date`
    error="${ts}: failed to publish on: ${broker}"
    echo $error >> heartbeat.log
fi

