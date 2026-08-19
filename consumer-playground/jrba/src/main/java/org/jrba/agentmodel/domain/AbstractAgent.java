package org.jrba.agentmodel.domain;

import static java.util.Collections.emptyList;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.constants.RuleSetTypeConstants.DEFAULT_RULE_SET;
import static org.jrba.rulesengine.constants.RuleTypeConstants.INITIALIZE_BEHAVIOURS_RULE;

import java.io.Serializable;
import java.util.List;

import org.jrba.agentmodel.behaviour.ListenForControllerObjects;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import jade.core.Agent;
import jade.core.behaviours.Behaviour;
import lombok.Getter;
import lombok.Setter;

/**
 * Abstract class representing JADE-based agent.
 * It should be extended by all specific agent types that are to be using rules.
 *
 * @param <T> type of node connected to the Agent
 * @param <E> type of properties of Agent
 */
@Getter
@Setter
public class AbstractAgent<T extends AgentNode<E>, E extends AgentProps> extends Agent implements
		Serializable {

	protected static final Logger logger = LoggerFactory.getLogger(AbstractAgent.class);
	protected T agentNode;
	protected E properties;
	protected RulesController<E, T> rulesController;

	/**
	 * Default constructor.
	 */
	public AbstractAgent() {
		setEnabledO2ACommunication(true, getObjectsNumber());
	}

	/**
	 * Abstract method used to validate if arguments of the given agent are correct
	 */
	protected void validateAgentArguments() {
		if (isNull(properties)) {
			logger.warn("Agent properties have not been set!");
		}
	}

	/**
	 * Abstract method used to initialize given agent data
	 *
	 * @param arguments arguments passed by the user
	 */
	protected void initializeAgent(final Object[] arguments) {
		//TO BE OVERRIDDEN BY USER
	}

	/**
	 * Abstract method that is used to prepare starting behaviours for given agente
	 *
	 * @return list of behaviours that are to be initially initiated by the Agent
	 */
	protected List<Behaviour> prepareStartingBehaviours() {
		return emptyList();
	}

	/**
	 * Abstract method responsible for running starting behaviours,
	 * By default
	 */
	protected void runStartingBehaviours() {
		addBehaviour(new ListenForControllerObjects(this, prepareStartingBehaviours(), getObjectsNumber()));
	}

	/**
	 * Abstract method responsible for running initial custom behaviours prepared only for selected rule set
	 */
	protected void runInitialBehavioursForRuleSet() {
		final RuleSetFacts facts = new RuleSetFacts(rulesController.getLatestLongTermRuleSetIdx().get());
		facts.put(RULE_TYPE, INITIALIZE_BEHAVIOURS_RULE);
		rulesController.fire(facts);
	}

	/**
	 * Method used to select rule based on given fact
	 *
	 * @param facts set of facts based on which given rule is triggered
	 */
	public void fireOnFacts(final RuleSetFacts facts) {
		if (nonNull(rulesController)) {
			rulesController.fire(facts);
		} else {
			logger.warn("Rules controller has not been initialized!");
		}
	}

	/**
	 * Method initialized rules controller and starts default agent behaviours.
	 *
	 * @param rulesController rules controller with which agent is to be connected
	 */
	public void setRulesController(RulesController<E, T> rulesController) {
		this.rulesController = rulesController;

		if (isNull(properties)) {
			logger.warn("Agent properties have not been set!");
		} else {
			properties.setAgentName(getName());
			if (nonNull(agentNode)) {
				properties.setAgentNode(agentNode);
			}
		}

		rulesController.setAgent(this, properties, agentNode, getDefaultRuleSet());
		runInitialBehavioursForRuleSet();
	}

	/**
	 * Method can be overridden in case the agent accepts some objects put into the agent.
	 *
	 * @return number of objects that are to be passed to the Agent before starting its behaviours.
	 */
	protected int getObjectsNumber() {
		return 0;
	}

	/**
	 * Method should be overridden in case the name of default rule set differs from "DEFAULT_RULE_SET".
	 *
	 * @return name of the default rule set run by the agent
	 */
	protected String getDefaultRuleSet() {
		return DEFAULT_RULE_SET;
	}

	@Override
	protected void setup() {
		final Object[] arguments = getArguments();

		initializeAgent(arguments);
		validateAgentArguments();
		runStartingBehaviours();
	}

	@Override
	protected void takeDown() {
		logger.info("I'm finished. Bye!");
		super.takeDown();
	}

}
