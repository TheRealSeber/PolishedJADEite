package org.jrba.rulesengine;

import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.utils.rules.RuleSetConstructor.constructRuleSetWithName;
import static org.jrba.utils.rules.RuleSetConstructor.modifyBaseRuleSetWithName;
import static org.jrba.utils.rules.RuleSetConstructor.modifyRuleSetForName;
import static org.slf4j.LoggerFactory.getLogger;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.slf4j.Logger;

import jade.core.Agent;
import lombok.Getter;

/**
 * Class provides functionalities that handle agent behaviours via rule sets
 *
 * @param <T> type of properties of Agent
 * @param <E> type of node connected to the Agent
 */
@Getter
public class RulesController<T extends AgentProps, E extends AgentNode<T>> {

	private static final Logger logger = getLogger(RulesController.class);
	protected Agent agent;
	protected E agentNode;
	protected T agentProps;
	protected AtomicInteger latestLongTermRuleSetIdx;
	protected AtomicInteger latestRuleSetIdx;
	protected ConcurrentMap<Integer, RuleSet> ruleSets;
	protected String baseRuleSet;

	/**
	 * Default constructor assigning initial controller's values.
	 */
	public RulesController() {
		latestLongTermRuleSetIdx = new AtomicInteger(0);
		latestRuleSetIdx = new AtomicInteger(0);
		ruleSets = new ConcurrentHashMap<>();
	}

	/**
	 * Method initialize agent values.
	 *
	 * @param agent       agent connected to the rules controller
	 * @param agentProps  agent properties
	 * @param agentNode   GUI agent node
	 * @param baseRuleSet name of the base rule set
	 */
	public void setAgent(Agent agent, T agentProps, E agentNode, String baseRuleSet) {
		this.agent = agent;
		this.agentProps = agentProps;
		this.agentNode = agentNode;
		this.baseRuleSet = baseRuleSet;

		final RuleSet ruleSet = constructRuleSetWithName(baseRuleSet, this);
		if (nonNull(ruleSet)) {
			this.ruleSets.put(latestLongTermRuleSetIdx.get(), ruleSet);
		}
	}

	/**
	 * Method fires agent rule set for a set of facts.
	 *
	 * @param facts set of facts based on which actions are going to be taken
	 */
	public void fire(final RuleSetFacts facts) {
		try {
			final RuleSet ruleSet = ruleSets.get((int) facts.get(RULE_SET_IDX));
			ruleSet.fireRuleSet(facts);
		} catch (NullPointerException e) {
			logger.warn("Couldn't find any rule set of given index! Rule type: {} Rule step: {}",
					facts.get(RULE_TYPE), facts.get(RULE_STEP));
		}
	}

	/**
	 * Method adds new agent's rule set.
	 *
	 * @param type type of rule set that is to be added
	 * @param idx  index of the added rule set
	 */
	public void addModifiedRuleSet(final String type, final int idx) {
		this.ruleSets.put(idx, modifyBaseRuleSetWithName(baseRuleSet, type, this));
		this.latestLongTermRuleSetIdx.set(idx);
		this.latestRuleSetIdx.set(idx);
	}

	/**
	 * Method adds new agent's rule set.
	 *
	 * @param modifications modifications to current rule set that are to be applied
	 * @param idx           index which is to be assigned to the new rule set
	 */
	public void addModifiedTemporaryRuleSetFromCurrent(final RuleSet modifications, final int idx) {
		final RuleSet connectedRuleSet = new RuleSet(modifications, this);
		this.ruleSets.put(idx,
				modifyRuleSetForName(ruleSets.get(latestLongTermRuleSetIdx.get()), connectedRuleSet));
		this.latestRuleSetIdx.set(idx);
	}

	/**
	 * Method adds new agent's rule set.
	 *
	 * @param name name of rule set that is to be added
	 * @param idx  index of the added ruleSet
	 */
	public void addNewRuleSet(final String name, final int idx) {
		this.ruleSets.put(idx, constructRuleSetWithName(name, this));
		this.latestLongTermRuleSetIdx.set(idx);
		this.latestRuleSetIdx.set(idx);
	}

	/**
	 * Method verifies if the rule set is to be removed from the controller.
	 *
	 * @param ruleSetForProcess map containing rule sets assigned to given process
	 *                          (used to check if there are no processes still undergoing for a
	 *                          rule set that is to be removed)
	 * @param ruleSetIdx        index of the rule set removed along with the object
	 * @return flag indicating if the rule set was removed
	 */
	public boolean removeRuleSet(final ConcurrentMap<String, Integer> ruleSetForProcess, final int ruleSetIdx) {
		if (ruleSetIdx != latestLongTermRuleSetIdx.get()
				&& ruleSetForProcess.values().stream().noneMatch(val -> val == ruleSetIdx)) {

			logger.info("Removing rule set {} from the map.", ruleSetIdx);
			ruleSets.remove(ruleSetIdx);
			return true;
		}
		return false;
	}
}
