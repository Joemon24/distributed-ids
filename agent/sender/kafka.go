package sender

import (
	"context"
	"encoding/json"
	"os"
	"time"

	"github.com/segmentio/kafka-go"
)

type KafkaSender struct {
	writer *kafka.Writer
}

func NewKafkaSender() *KafkaSender {
	return &KafkaSender{
		writer: &kafka.Writer{
			Addr:         kafka.TCP(os.Getenv("REDPANDA_BROKERS")),
			Topic:        os.Getenv("REDPANDA_TOPIC"),
			RequiredAcks: kafka.RequireAll,
			Balancer:     &kafka.LeastBytes{},
		},
	}
}

func (k *KafkaSender) Send(batch any) error {
	data, err := json.Marshal(batch)
	if err != nil {
		return err
	}

	return k.writer.WriteMessages(
		context.Background(),
		kafka.Message{
			Value: data,
			Time:  time.Now(),
		},
	)
}

func (k *KafkaSender) Close() error {
	return k.writer.Close()
}

