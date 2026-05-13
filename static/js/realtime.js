class SSEClient {
    constructor(url, handlers) {
        this._handlers = handlers;
        this._source = new EventSource(url);
        this._source.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (this._handlers[msg.type]) this._handlers[msg.type](msg);
            } catch {}
        };
    }
    close() { this._source.close(); }
}
