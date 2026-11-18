# Host unit test for firmware/common. No SDK required.
#   make -C firmware/common/test
CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O1 -g
INC := -I../include
OUT := $(CURDIR)/build

all: run

$(OUT)/test_bridge_proto: test_bridge_proto.c ../src/bridge_proto.c ../include/uwbrl/*.h
	mkdir -p $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ test_bridge_proto.c ../src/bridge_proto.c

run: $(OUT)/test_bridge_proto
	$(OUT)/test_bridge_proto

clean:
	rm -rf $(OUT)

.PHONY: all run clean
