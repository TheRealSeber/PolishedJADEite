package org.jrba.agentmodel.domain.node;

import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.environment.domain.ExternalEvent;
import org.jrba.environment.websocket.GuiWebSocketClient;

import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Class represents generic agent node used to connect agent with external environment
 *
 * @param <E> type of properties used by the Agent
 */
@Getter
@NoArgsConstructor
public abstract class AgentNode<E extends AgentProps> {

	protected final Queue<ExternalEvent> eventsQueue = new ConcurrentLinkedQueue<>();
	protected GuiWebSocketClient mainWebSocket;
	protected String agentName;
	protected String agentType;

	/**
	 * Class constructor
	 *
	 * @param name      agent name
	 * @param agentType type of agent node
	 */
	protected AgentNode(final String name, final String agentType) {
		this.agentName = name;
		this.agentType = agentType;
	}

	/**
	 * Method updates interface of given agent node
	 *
	 * @param props properties of the Agent
	 */
	public abstract void updateGUI(final E props);

	/**
	 * Method saves monitoring data of given agent node.
	 * This method can optionally be applied to agents in order to incorporate the database.
	 *
	 * @param props properties of the Agent
	 */
	public abstract void saveMonitoringData(final E props);

	/**
	 * Method that can be used to initialize node communication socket.
	 * By itself, it does nothing. However, it can be extended to provide system-specific implementation.
	 *
	 * @param url url of the WebSocket to which the AgentNode is to be connected
	 * @return connected GuiWebSocketClient
	 */
	public abstract GuiWebSocketClient initializeSocket(final String url);

	/**
	 * Method used to add next event to the agent node's queue.
	 *
	 * @param event new event that is to be added to the queue
	 */
	public void addEvent(final ExternalEvent event) {
		eventsQueue.add(event);
	}

	/**
	 * Method that can be used to connect socket base on given url.
	 *
	 * @param url url of the WebSocket to which the AgentNode is to be connected
	 * @throws InterruptedException when connection to the Websocket is interrupted
	 */
	public void connectSocket(final String url) throws InterruptedException {
		mainWebSocket = initializeSocket(url);
		mainWebSocket.connectBlocking();
	}

	@Override
	public boolean equals(Object o) {
		if (this == o)
			return true;
		if (o == null || getClass() != o.getClass())
			return false;
		AgentNode<?> agentNode = (AgentNode<?>) o;
		return Objects.equals(agentName, agentNode.agentName) && Objects.equals(agentType,
				agentNode.agentType);
	}

	@Override
	public int hashCode() {
		return Objects.hash(agentName, agentType);
	}
}
