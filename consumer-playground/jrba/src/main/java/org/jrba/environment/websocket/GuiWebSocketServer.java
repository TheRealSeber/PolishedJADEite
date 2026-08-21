package org.jrba.environment.websocket;

import static java.util.Objects.nonNull;

import java.net.InetSocketAddress;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Custom websocket server that can be used to simulate external environment
 * (e.g. can be used in case of the systems without GUI)
 */
public class GuiWebSocketServer extends WebSocketServer {

	private static final Logger logger = LoggerFactory.getLogger(GuiWebSocketServer.class);

	public GuiWebSocketServer() {
		super(new InetSocketAddress(8080));
	}

	public GuiWebSocketServer(final int port) {
		super(new InetSocketAddress(port));
	}

	@Override
	public void onOpen(final WebSocket conn, final ClientHandshake handshake) {
		conn.send("Welcoming message!");
	}

	@Override
	public void onClose(final WebSocket conn, final int code, final String reason, final boolean remote) {
		logger.warn("Connection closed by {}, code: {}, reason: {} ", remote ? "remote peer" : "us", code, reason);
	}

	@Override
	public void onMessage(final WebSocket conn, final String message) {
		getConnections().stream()
				.filter(connection -> !connection.equals(conn))
				.forEach(connection -> connection.send(message));
	}

	@Override
	public void onError(final WebSocket conn, final Exception ex) {
		logger.error("WebSocket error! {}", ex.getMessage());

		if (nonNull(conn)) {
			conn.close();
		}
	}

	@Override
	public void onStart() {
		logger.info("Starting websocket server!");
	}
}
