package org.jrba.utils.factory;

import static jade.wrapper.AgentController.ASYNC;
import static java.util.Arrays.asList;
import static java.util.Collections.singletonList;
import static java.util.Objects.nonNull;
import static java.util.concurrent.Executors.newSingleThreadScheduledExecutor;
import static java.util.concurrent.TimeUnit.HOURS;
import static java.util.concurrent.TimeUnit.MILLISECONDS;
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.jrba.rulesengine.rest.RuleSetRestApi.addAgentNode;
import static org.jrba.utils.factory.constants.AgentControllerConstants.INITIALIZATION_DELAY;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import org.jrba.agentmodel.domain.args.AgentArgs;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.exception.JadeControllerException;
import org.jrba.rulesengine.RulesController;

import jade.wrapper.AgentController;
import jade.wrapper.ContainerController;
import jade.wrapper.StaleProxyException;
import lombok.AllArgsConstructor;

/**
 * Class provides basic functionalities for initialization of agent controllers.
 */
@AllArgsConstructor
@SuppressWarnings("rawtypes")
public class AgentControllerFactoryImpl implements AgentControllerFactory {

	protected final ContainerController containerController;

	@Override
	public AgentController createAgentController(final AgentArgs agentArgs, final String className) {
		final RulesController<?, ?> rulesController = new RulesController<>();

		try {
			final List<Object> argumentsToPass = new ArrayList<>(singletonList(rulesController));
			final Object[] agentArguments = agentArgs.getObjectArray();
			argumentsToPass.addAll(asList(agentArguments));

			return containerController.createNewAgent(agentArgs.getName(), className, argumentsToPass.toArray());
		} catch (StaleProxyException e) {
			Thread.currentThread().interrupt();
			throw new JadeControllerException("Failed to run custom agent controller", e);
		}
	}

	@Override
	public AgentController connectAgentController(final AgentController agentController, final AgentNode agentNode) {
		try {
			if (nonNull(agentController)) {
				final RulesController<?, ?> rulesController = new RulesController<>();
				addAgentNode(agentNode);
				agentController.putO2AObject(agentNode, ASYNC);
				agentController.putO2AObject(rulesController, ASYNC);
			}

			return agentController;
		} catch (StaleProxyException e) {
			throw new JadeControllerException("Failed to pass objects to agent controller", e);
		}
	}

	@Override
	public void runAgentControllers(final List<AgentController> controllers, final long agentRunDelay) {
		var scheduledExecutor = newSingleThreadScheduledExecutor();
		scheduledExecutor.schedule(
				() -> controllers.forEach(controller -> runAgentController(controller, agentRunDelay)),
				INITIALIZATION_DELAY, SECONDS);
		shutdownAndAwaitTermination(scheduledExecutor, 1, HOURS);
	}

	@Override
	public void runAgentController(final AgentController controller, long pause) {
		try {
			controller.start();
			controller.activate();
			MILLISECONDS.sleep(pause);
		} catch (StaleProxyException | InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new JadeControllerException("Failed to run agent controller", e);
		}
	}

	@Override
	public void shutdownAndAwaitTermination(final ExecutorService executorService,
			final int timeout, final TimeUnit timeoutUnit) {
		executorService.shutdown();
		try {
			if (!executorService.awaitTermination(timeout, timeoutUnit)) {
				executorService.shutdownNow();
			}
		} catch (InterruptedException ie) {
			executorService.shutdownNow();
			Thread.currentThread().interrupt();
		}
	}
}
