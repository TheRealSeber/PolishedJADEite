package org.jrba.utils.rules;

import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.rest.RuleSetRestApi.getAvailableRuleSets;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.CFP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.COMBINED;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.LISTENER;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.LISTENER_SINGLE;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.PERIODIC;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.PROPOSAL;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.REQUEST;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SCHEDULED;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SEARCH;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SUBSCRIPTION;
import static org.slf4j.LoggerFactory.getLogger;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.BiPredicate;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.combined.AgentCombinedRule;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.types.ruletype.AgentRuleType;
import org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum;
import org.slf4j.Logger;

/**
 * Class storing methods used to construct rule sets
 */
@SuppressWarnings("unchecked")
public class RuleSetConstructor {

	public static final List<AgentRuleType> stepBasedRules = List.of(CFP, LISTENER, LISTENER_SINGLE, PERIODIC,
			REQUEST, SCHEDULED, SEARCH, SUBSCRIPTION, PROPOSAL);
	private static final Logger logger = getLogger(RuleSetConstructor.class);

	/**
	 * Method constructs rule set for given name
	 *
	 * @param name       name of rule set
	 * @param controller controller which runs given rule set
	 * @return connected RuleSet
	 */
	public static <E extends AgentProps, T extends AgentNode<E>> RuleSet constructRuleSetWithName(
			final String name, final RulesController<E, T> controller) {
		return getRuleSetTemplate(name, controller);
	}

	/**
	 * Method constructs modifies existing rule set by exchanging some rules with the rules coming from modified rule set.
	 *
	 * @param baseName   name of base rule set that is to be modified
	 * @param name       name of rule set which rules are to be used as modifications
	 * @param controller controller which runs given rule set
	 * @return constructed RuleSet
	 */
	public static <E extends AgentProps, T extends AgentNode<E>> RuleSet modifyBaseRuleSetWithName(
			final String baseName, final String name, final RulesController<E, T> controller) {
		final RuleSet baseRuleSet = getRuleSetTemplate(baseName, controller);
		final RuleSet modifications = getRuleSetTemplate(name, controller);
		return modifyRuleSetForName(baseRuleSet, modifications);
	}

	/**
	 * Method constructs modified rule set (modifications are applied to default rule set)
	 *
	 * @param baseRuleSet   base rule set which is to be modified
	 * @param modifications rule set which modifications are to be applied
	 * @return constructed RuleSet
	 */
	public static RuleSet modifyRuleSetForName(final RuleSet baseRuleSet, final RuleSet modifications) {
		if (nonNull(modifications) && nonNull(baseRuleSet)) {
			final RuleSet baseRules = new RuleSet(baseRuleSet);
			final List<AgentRule> modificationRules = new ArrayList<>((modifications.getAgentRules()));
			final BiPredicate<AgentRule, AgentRule> testIfMatch = (baseRule, modificationRule) ->
					baseRule.getRuleType().equals(modificationRule.getRuleType()) &&
							baseRule.getAgentType().equals(modificationRule.getAgentType());
			baseRules.setName(modifications.getName());

			if (modificationRules.isEmpty()) {
				return baseRules;
			}

			final List<AgentRule> modifiableRules = baseRules.getAgentRules().stream()
					.filter(agentRule -> modificationRules.stream().anyMatch(rule -> testIfMatch.test(agentRule, rule)))
					.toList();

			final List<AgentRule> usedModificationsCombined =
					performModificationOfCombinedRules(modifiableRules, modifications, modificationRules, baseRules);
			final List<AgentRule> usedModificationsStepBased =
					performModificationOfStepBasedRules(modifiableRules, modifications, modificationRules, baseRules);
			final List<AgentRule> remainingModifications = modifications.getAgentRules().stream()
					.filter(modification -> !usedModificationsCombined.contains(modification) &&
							!usedModificationsStepBased.contains(modification))
					.toList();

			baseRules.getAgentRules().removeIf(agentRule -> modificationRules.stream()
					.anyMatch(rule -> testIfMatch.test(agentRule, rule)));
			baseRules.getAgentRules().addAll(remainingModifications);
			return baseRules;
		}
		return baseRuleSet;
	}

	/**
	 * Method constructs rule set from the existing rest templates
	 *
	 * @param ruleSetName name of th rule set that is to be used
	 * @param controller  controller with which rule set is to be connected
	 * @return connected with the controller rule set
	 */
	public static <E extends AgentProps, T extends AgentNode<E>> RuleSet getRuleSetTemplate(
			final String ruleSetName, final RulesController<E, T> controller) {
		if (nonNull(getAvailableRuleSets()) && getAvailableRuleSets().containsKey(ruleSetName)) {
			final RuleSet ruleSetTemplate = getAvailableRuleSets().get(ruleSetName);
			return new RuleSet(ruleSetTemplate, controller);
		} else {
			logger.info("Rule set {} not found!", ruleSetName);
			return null;
		}
	}

	private static List<AgentRule> performModificationOfCombinedRules(final List<AgentRule> originalRules,
			final RuleSet modifications, final List<AgentRule> modificationRules, final RuleSet baseSet) {
		return originalRules.stream()
				.filter(agentRule -> agentRule.getAgentRuleType().equals(COMBINED.getType()))
				.map(agentRule -> copyAndRemoveRule(agentRule, baseSet))
				.map(AgentCombinedRule.class::cast)
				.map(agentRule -> modifyCombinedRule(agentRule, modifications, modificationRules, baseSet))
				.flatMap(Collection::stream)
				.toList();
	}

	private static List<AgentRule> performModificationOfStepBasedRules(final List<AgentRule> originalRules,
			final RuleSet modifications, final List<AgentRule> modificationRules, final RuleSet baseSet) {
		return originalRules.stream()
				.filter(agentRule -> stepBasedRules.contains(AgentRuleTypeEnum.valueOf(agentRule.getAgentRuleType())))
				.map(agentRule -> copyAndRemoveRule(agentRule, baseSet))
				.map(AgentBasicRule.class::cast)
				.map(agentRule -> modifyStepBasedRule(agentRule, modifications, modificationRules, baseSet))
				.flatMap(Collection::stream)
				.toList();
	}

	private static AgentRule copyAndRemoveRule(final AgentRule rule, final RuleSet baseSet) {
		baseSet.getAgentRules().remove(rule);
		return rule.copy();
	}

	private static <E extends AgentProps, T extends AgentNode<E>> List<AgentRule> modifyStepBasedRule(
			final AgentBasicRule<E, T> stepBasedRule, final RuleSet modifications,
			final List<AgentRule> modificationRules, final RuleSet baseSet) {

		final List<String> stepRules = stepBasedRule.getRules().stream().map(AgentRule::getStepType).toList();
		final List<AgentRule> applicableModifications = modifications.getAgentRules().stream()
				.filter(rule -> stepRules.contains(rule.getStepType()))
				.toList();
		final List<String> consideredTypes = applicableModifications.stream().map(AgentRule::getStepType)
				.toList();
		modificationRules.removeIf(agentRule -> agentRule.getRuleType().equals(stepBasedRule.getRuleType()) &&
				agentRule.getAgentType().equals(stepBasedRule.getAgentType()) &&
				nonNull(agentRule.getStepType()) &&
				consideredTypes.contains(agentRule.getStepType()));

		if (!applicableModifications.isEmpty()) {
			stepBasedRule.getRules().removeIf(stepRule -> consideredTypes.contains(stepRule.getStepType()));
			stepBasedRule.getRules().addAll(applicableModifications);
		}
		baseSet.getAgentRules().add(stepBasedRule);

		return new ArrayList<>(applicableModifications);
	}

	private static <E extends AgentProps, T extends AgentNode<E>> List<AgentRule> modifyCombinedRule(
			final AgentCombinedRule<E, T> combinedRule, final RuleSet modifications,
			final List<AgentRule> modificationRules, final RuleSet baseSet) {

		final List<String> subRules = combinedRule.getNestedRules();
		final List<AgentRule> applicableModifications = modifications.getAgentRules().stream()
				.filter(rule -> rule.getRuleType().equals(combinedRule.getRuleType()))
				.filter(rule -> rule.getAgentType().equals(combinedRule.getAgentType()))
				.filter(rule -> subRules.contains(rule.getSubRuleType()))
				.toList();
		final List<String> consideredTypes = applicableModifications.stream().map(AgentRule::getSubRuleType).toList();
		modificationRules.removeIf(agentRule -> agentRule.getRuleType().equals(combinedRule.getRuleType()) &&
				agentRule.getAgentType().equals(combinedRule.getAgentType()) &&
				nonNull(agentRule.getSubRuleType()) &&
				consideredTypes.contains(agentRule.getSubRuleType()));

		if (!applicableModifications.isEmpty()) {
			combinedRule.getRulesToCombine().removeIf(subRule -> consideredTypes.contains(subRule.getSubRuleType()));
			combinedRule.getRulesToCombine().addAll(applicableModifications);
		}
		baseSet.getAgentRules().add(combinedRule);

		return new ArrayList<>(applicableModifications);
	}
}
