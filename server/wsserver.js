'use strict';

// Минимальный сервер WebSocket (RFC 6455) без внешних зависимостей:
// приложение разворачивается одной командой `node server/index.js`.

const crypto = require('crypto');
const { EventEmitter } = require('events');

const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

const OPCODE = {
  CONTINUATION: 0x0,
  TEXT: 0x1,
  BINARY: 0x2,
  CLOSE: 0x8,
  PING: 0x9,
  PONG: 0xa,
};

const MAX_MESSAGE_BYTES = 1 << 20; // 1 МБ с большим запасом на игровые сообщения

class WebSocketConnection extends EventEmitter {
  constructor(socket) {
    super();
    this.socket = socket;
    this.closed = false;
    this.isAlive = true;
    this.buffer = Buffer.alloc(0);
    this.fragments = [];
    this.fragmentOpcode = null;

    socket.on('data', (chunk) => this._onData(chunk));
    socket.on('error', () => this.destroy());
    socket.on('close', () => this._onClose());
  }

  send(data) {
    if (this.closed) return;
    const payload = Buffer.from(typeof data === 'string' ? data : JSON.stringify(data), 'utf8');
    this._writeFrame(OPCODE.TEXT, payload);
  }

  ping() {
    if (!this.closed) this._writeFrame(OPCODE.PING, Buffer.alloc(0));
  }

  close(code = 1000, reason = '') {
    if (this.closed) return;
    const reasonBuffer = Buffer.from(reason, 'utf8');
    const payload = Buffer.alloc(2 + reasonBuffer.length);
    payload.writeUInt16BE(code, 0);
    reasonBuffer.copy(payload, 2);
    this._writeFrame(OPCODE.CLOSE, payload);
    this.closed = true;
    this.socket.end();
  }

  destroy() {
    if (this.closed) return;
    this.closed = true;
    this.socket.destroy();
  }

  _onClose() {
    if (!this.closed) this.closed = true;
    this.emit('close');
  }

  _writeFrame(opcode, payload) {
    const length = payload.length;
    let header;
    if (length < 126) {
      header = Buffer.alloc(2);
      header[1] = length;
    } else if (length < 65536) {
      header = Buffer.alloc(4);
      header[1] = 126;
      header.writeUInt16BE(length, 2);
    } else {
      header = Buffer.alloc(10);
      header[1] = 127;
      header.writeBigUInt64BE(BigInt(length), 2);
    }
    header[0] = 0x80 | opcode; // FIN + опкод, сервер не маскирует
    try {
      this.socket.write(Buffer.concat([header, payload]));
    } catch {
      this.destroy();
    }
  }

  _onData(chunk) {
    this.buffer = this.buffer.length ? Buffer.concat([this.buffer, chunk]) : chunk;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const frame = this._readFrame();
      if (!frame) break;
      this._handleFrame(frame);
      if (this.closed) break;
    }
  }

  // Возвращает разобранный кадр или null, если данных пока недостаточно.
  _readFrame() {
    const buf = this.buffer;
    if (buf.length < 2) return null;

    const fin = (buf[0] & 0x80) !== 0;
    const opcode = buf[0] & 0x0f;
    const masked = (buf[1] & 0x80) !== 0;
    let length = buf[1] & 0x7f;
    let offset = 2;

    if (length === 126) {
      if (buf.length < offset + 2) return null;
      length = buf.readUInt16BE(offset);
      offset += 2;
    } else if (length === 127) {
      if (buf.length < offset + 8) return null;
      const big = buf.readBigUInt64BE(offset);
      if (big > BigInt(MAX_MESSAGE_BYTES)) {
        this.close(1009, 'Сообщение слишком большое');
        return null;
      }
      length = Number(big);
      offset += 8;
    }

    if (length > MAX_MESSAGE_BYTES) {
      this.close(1009, 'Сообщение слишком большое');
      return null;
    }

    let mask = null;
    if (masked) {
      if (buf.length < offset + 4) return null;
      mask = buf.subarray(offset, offset + 4);
      offset += 4;
    }

    if (buf.length < offset + length) return null;

    const payload = Buffer.from(buf.subarray(offset, offset + length));
    if (mask) {
      for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
    }
    this.buffer = buf.subarray(offset + length);
    return { fin, opcode, payload };
  }

  _handleFrame(frame) {
    switch (frame.opcode) {
      case OPCODE.PING:
        this._writeFrame(OPCODE.PONG, frame.payload);
        break;
      case OPCODE.PONG:
        this.isAlive = true;
        break;
      case OPCODE.CLOSE:
        this.close(1000, '');
        break;
      case OPCODE.TEXT:
      case OPCODE.BINARY:
      case OPCODE.CONTINUATION: {
        if (frame.opcode !== OPCODE.CONTINUATION) {
          this.fragmentOpcode = frame.opcode;
          this.fragments = [];
        }
        this.fragments.push(frame.payload);
        const size = this.fragments.reduce((sum, part) => sum + part.length, 0);
        if (size > MAX_MESSAGE_BYTES) {
          this.close(1009, 'Сообщение слишком большое');
          return;
        }
        if (!frame.fin) return;
        const message = Buffer.concat(this.fragments);
        this.fragments = [];
        if (this.fragmentOpcode === OPCODE.TEXT) {
          this.isAlive = true;
          this.emit('message', message.toString('utf8'));
        }
        break;
      }
      default:
        this.close(1002, 'Неизвестный опкод');
    }
  }
}

// Подключается к обычному http.Server и обслуживает апгрейды на указанном пути.
function attachWebSocketServer(httpServer, { path = '/ws', heartbeatMs = 25000 } = {}) {
  const emitter = new EventEmitter();
  const connections = new Set();

  httpServer.on('upgrade', (req, socket) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname !== path) {
      socket.destroy();
      return;
    }
    const key = req.headers['sec-websocket-key'];
    if (req.headers.upgrade?.toLowerCase() !== 'websocket' || !key) {
      socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
      socket.destroy();
      return;
    }

    const accept = crypto.createHash('sha1').update(key + GUID).digest('base64');
    socket.write(
      'HTTP/1.1 101 Switching Protocols\r\n' +
        'Upgrade: websocket\r\n' +
        'Connection: Upgrade\r\n' +
        `Sec-WebSocket-Accept: ${accept}\r\n\r\n`
    );
    socket.setNoDelay(true);

    const connection = new WebSocketConnection(socket);
    connections.add(connection);
    connection.on('close', () => connections.delete(connection));
    emitter.emit('connection', connection, req);
  });

  // Пингуем клиентов и отключаем тех, кто перестал отвечать.
  const heartbeat = setInterval(() => {
    for (const connection of connections) {
      if (!connection.isAlive) {
        connection.destroy();
        continue;
      }
      connection.isAlive = false;
      connection.ping();
    }
  }, heartbeatMs);
  heartbeat.unref?.();

  emitter.connections = connections;
  emitter.stop = () => clearInterval(heartbeat);
  return emitter;
}

module.exports = { attachWebSocketServer, WebSocketConnection };
