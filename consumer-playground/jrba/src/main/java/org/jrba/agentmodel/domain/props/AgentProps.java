package org.jrba.agentmodel.domain.props;

import static java.util.Objects.nonNull;
import static org.jrba.agentmodel.types.AgentTypeEnum.BASIC;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import org.jeasy.rules.api.Facts;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.types.AgentType;

import lombok.Getter;
import lombok.Setter;

/**
 * Abstract class extended by classes representing properties of individual agent types.
 * (Note: raw and unchecked types are to be handled with more care in the future releases.)
 */
@Getter
@Setter
@SuppressWarnings({ "rawtypes", "unchecked" })
public class AgentProps {

	protected String agentName;
	protected AgentNode agentNode;
	protected String agentType;
	protected Map<String, Map<String, Object>> systemKnowledge;
	protected Facts agentKnowledge;

	/**
	 * Default constructor that sets the type of the agent
	 *
	 * @param agentName name of the agent
	 */
	public AgentProps(final String agentName) {
		this.agentType = BASIC.getName();
		this.agentName = agentName;
		this.systemKnowledge = new HashMap<>();
		this.agentKnowledge = new Facts();
	}

	/**
	 * Default constructor that sets the type of the agent
	 *
	 * @param agentType type of the agent
	 * @param agentName name of the agent
	 */
	public AgentProps(final AgentType agentType, final String agentName) {
		this.agentType = agentType.getName();
		this.agentName = agentName;
		this.systemKnowledge = new HashMap<>();
		this.agentKnowledge = new Facts();
	}

	/**
	 * Default constructor that sets the type of the agent
	 *
	 * @param agentType name of the agent type
	 * @param agentName name of the agent
	 */
	public AgentProps(final String agentType, final String agentName) {
		this.agentType = agentType;
		this.agentName = agentName;
		this.systemKnowledge = new HashMap<>();
		this.agentKnowledge = new Facts();
	}

	/**
	 * Method used in updating interface associated with given agent (to be overridden).
	 */
	public void updateGUI() {
		if (nonNull(agentNode)) {
			agentNode.updateGUI(this);
		}
	}

	/**
	 * Method used to store monitoring data.
	 */
	public void saveMonitoringData() {
		if (nonNull(agentNode)) {
			agentNode.saveMonitoringData(this);
		}
	}

	@Override
	public boolean equals(Object o) {
		if (this == o)
			return true;
		if (o == null || getClass() != o.getClass())
			return false;
		AgentProps that = (AgentProps) o;
		return Objects.equals(agentName, that.agentName) && Objects.equals(agentType, that.agentType);
	}

	@Override
	public int hashCode() {
		return Objects.hash(agentName, agentType);
	}
}
