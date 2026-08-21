package org.jrba.rulesengine.behaviour.listen;

import static java.lang.System.currentTimeMillis;
import static java.util.Optional.ofNullable;
import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_EXPIRATION;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_TEMPLATE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RECEIVED_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SINGLE_MESSAGE_READER_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SINGLE_MESSAGE_READER_HANDLE_MESSAGE_STEP;

import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.proto.states.MsgReceiver;

/**
 * Abstract behaviour providing template to handle single and scheduled message retrieval
 */
public class ListenForSingleMessage extends MsgReceiver {

	protected RuleSetFacts facts;
	protected RulesController<?, ?> controller;

	private ListenForSingleMessage(final Agent agent, final RuleSetFacts facts,
			final RulesController<?, ?> controller) {
		super(agent, facts.get(MESSAGE_TEMPLATE), (long) facts.get(MESSAGE_EXPIRATION) + currentTimeMillis(),
				null, null);

		this.facts = facts;
		this.controller = controller;
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts used in single message receiver
	 * @param ruleType   type of the rule that handles single message receiver
	 * @param controller rules controller
	 * @return ListenForSingleMessage
	 */
	public static ListenForSingleMessage create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, SINGLE_MESSAGE_READER_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new ListenForSingleMessage(agent, methodFacts, controller);
	}

	@Override
	protected void handleMessage(ACLMessage msg) {
		facts.put(RULE_STEP, SINGLE_MESSAGE_READER_HANDLE_MESSAGE_STEP.getType());
		facts.put(RECEIVED_MESSAGE, ofNullable(msg));
		controller.fire(facts);
	}
}
