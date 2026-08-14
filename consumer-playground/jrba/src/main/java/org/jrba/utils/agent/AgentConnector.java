package org.jrba.utils.agent;

import static org.slf4j.LoggerFactory.getLogger;

import org.jrba.agentmodel.domain.AbstractAgent;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.rulesengine.RulesController;
import org.slf4j.Logger;

/**
 * Class defines set of utilities used to connect agents with object instances.
 */
@SuppressWarnings({ "unchecked", "rawtypes" })
public abstract class AgentConnector {

	private static final Logger logger = getLogger(AgentConnector.class);

	/**
	 * Method connects agent with given object.
	 * Method can be overridden in case of more types of controllers
	 *
	 * @param abstractAgent agent to be connected with object
	 * @param currentObject object to be connected with agent
	 */
	public static void connectAgentObject(AbstractAgent abstractAgent, Object currentObject) {
		if (currentObject instanceof AgentNode node) {
			abstractAgent.setAgentNode(node);
			logger.info("[{}] Agent connected with the GUI controller", abstractAgent.getName());
		} else if (currentObject instanceof RulesController rulesController) {
			abstractAgent.setRulesController(rulesController);
			logger.info("[{}] Agent connected with the rules controller", abstractAgent.getName());
		}
	}

}
