package org.jrba.environment.domain;

import java.io.Serializable;
import java.time.Instant;
import java.util.Map;

import org.jrba.environment.types.EventType;
import org.jrba.agentmodel.domain.node.AgentNode;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Class represents the abstract event which may occur in the environment
 */
@Getter
@AllArgsConstructor
@SuppressWarnings("rawtypes")
public abstract class ExternalEvent implements Serializable {

	protected String agentName;
	protected EventType eventType;
	protected Instant occurrenceTime;

	/**
	 * Method responsible for triggering a given event
	 *
	 * @param agentNodes all nodes present in the system
	 * @param <T> type of the AgentNode
	 */
	public abstract <T extends AgentNode> void trigger(final Map<String, T> agentNodes);
}
