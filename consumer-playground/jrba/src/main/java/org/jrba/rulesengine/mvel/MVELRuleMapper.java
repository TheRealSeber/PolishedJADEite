package org.jrba.rulesengine.mvel;

import org.jrba.rulesengine.rest.domain.BehaviourRuleRest;
import org.jrba.rulesengine.rest.domain.CallForProposalRuleRest;
import org.jrba.rulesengine.rest.domain.CombinedRuleRest;
import org.jrba.rulesengine.rest.domain.MessageListenerRuleRest;
import org.jrba.rulesengine.rest.domain.PeriodicRuleRest;
import org.jrba.rulesengine.rest.domain.ProposalRuleRest;
import org.jrba.rulesengine.rest.domain.RequestRuleRest;
import org.jrba.rulesengine.rest.domain.RuleRest;
import org.jrba.rulesengine.rest.domain.ScheduledRuleRest;
import org.jrba.rulesengine.rest.domain.SearchRuleRest;
import org.jrba.rulesengine.rest.domain.SingleMessageListenerRuleRest;
import org.jrba.rulesengine.rest.domain.SubscriptionRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.combined.AgentCombinedRule;
import org.jrba.rulesengine.rule.simple.AgentBehaviourRule;
import org.jrba.rulesengine.rule.simple.AgentChainRule;
import org.jrba.rulesengine.rule.template.AgentCFPRule;
import org.jrba.rulesengine.rule.template.AgentMessageListenerRule;
import org.jrba.rulesengine.rule.template.AgentPeriodicRule;
import org.jrba.rulesengine.rule.template.AgentProposalRule;
import org.jrba.rulesengine.rule.template.AgentRequestRule;
import org.jrba.rulesengine.rule.template.AgentScheduledRule;
import org.jrba.rulesengine.rule.template.AgentSearchRule;
import org.jrba.rulesengine.rule.template.AgentSingleMessageListenerRule;
import org.jrba.rulesengine.rule.template.AgentSubscriptionRule;
import org.jrba.rulesengine.ruleset.RuleSet;

/**
 * Class containing methods to map rules obtained using MVEL expressions
 */
public class MVELRuleMapper {

	/**
	 * Method maps the REST rule type to the AgentRule.
	 *
	 * @param ruleRest rest rule representation
	 * @param ruleSet  rule set
	 * @return constructed AgentRule
	 */
	public static AgentRule getRuleForType(final RuleRest ruleRest, final RuleSet ruleSet) {
		return switch (ruleRest.getAgentRuleType()) {
			case "SCHEDULED" -> new AgentScheduledRule<>((ScheduledRuleRest) ruleRest);
			case "PERIODIC" -> new AgentPeriodicRule<>((PeriodicRuleRest) ruleRest);
			case "PROPOSAL" -> new AgentProposalRule<>((ProposalRuleRest) ruleRest);
			case "REQUEST" -> new AgentRequestRule<>((RequestRuleRest) ruleRest);
			case "BEHAVIOUR" -> new AgentBehaviourRule<>((BehaviourRuleRest) ruleRest);
			case "SEARCH" -> new AgentSearchRule<>((SearchRuleRest) ruleRest);
			case "CFP" -> new AgentCFPRule<>((CallForProposalRuleRest) ruleRest);
			case "SUBSCRIPTION" -> new AgentSubscriptionRule<>((SubscriptionRuleRest) ruleRest);
			case "LISTENER_SINGLE" -> new AgentSingleMessageListenerRule<>((SingleMessageListenerRuleRest) ruleRest);
			case "COMBINED" -> new AgentCombinedRule<>((CombinedRuleRest) ruleRest, ruleSet);
			case "CHAIN" -> new AgentChainRule<>(ruleRest, ruleSet);
			case "LISTENER" -> new AgentMessageListenerRule<>((MessageListenerRuleRest) ruleRest, ruleSet);
			default -> new AgentBasicRule<>(ruleRest);
		};
	}
}
