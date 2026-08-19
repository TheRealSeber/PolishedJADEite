package org.jrba.environment.websocket;

import static org.jrba.utils.mapper.JsonMapper.getMapper;

import java.net.URI;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.jrba.exception.IncorrectMessageContentException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.fasterxml.jackson.core.JsonProcessingException;

/**
 * Websocket client used to connect system agents with external environment
 */
public class GuiWebSocketClient extends WebSocketClient {

	private static final Logger logger = LoggerFactory.getLogger(GuiWebSocketClient.class);

	/**
	 * Method used only for the purpose of testing.
	 */
	public GuiWebSocketClient() {
		super(URI.create(""));
	}

	/**
	 * Default constructor.
	 *
	 * @param serverUri address of the Websocket
	 */
	public GuiWebSocketClient(final URI serverUri) {
		super(serverUri);
	}

	/**
	 * Method that should be inherited in order to handle received messages
	 *
	 * @param message message received via websocket
	 */
	public void send(Object message) {
		try {
			if (super.isOpen()) {
				super.send(getMapper().writeValueAsString(message));
			}
		} catch (final JsonProcessingException e) {
			throw new IncorrectMessageContentException();
		}
	}

	@Override
	public void onOpen(ServerHandshake serverHandshake) {
		logger.info("Connected to WebSocket server");
	}

	@Override
	public void onMessage(String message) {
		logger.debug("Received message from WebSocket server: {}", message);
	}

	@Override
	public void onClose(int code, String reason, boolean remote) {
		logger.warn("Connection closed by {}, code: {}, reason: {} ", remote ? "remote peer" : "us", code, reason);
	}

	@Override
	public void onError(Exception e) {
		logger.error("WebSocket error! {}", e.getMessage());
	}

	@Override
	public void connect() {
		if (!isOpen()) {
			super.connect();
		}
	}
}
