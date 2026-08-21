package org.jrba.utils.factory;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import org.jrba.agentmodel.domain.args.AgentArgs;
import org.jrba.agentmodel.domain.node.AgentNode;

import jade.wrapper.AgentController;

/**
 * Factory used to create and run agent controllers
 */
@SuppressWarnings("rawtypes")
public interface AgentControllerFactory {

	/**
	 * Method creates the agent controllers
	 *
	 * @param agentArgs agent arguments
	 * @param className name of the class from which the agent is to be created
	 * @return AgentController that can be started
	 */
	AgentController createAgentController(final AgentArgs agentArgs, final String className);

	/**
	 * Method connects the agent controller
	 *
	 * @param agentController controller that is to be connected
	 * @param agentNode       interface node that is to be connected with the controller
	 * @return AgentController that can be started
	 */
	AgentController connectAgentController(final AgentController agentController, final AgentNode agentNode);

	/**
	 * Method runs the agent controllers
	 *
	 * @param controllers   controllers that are to be run
	 * @param agentRunDelay delay after which the agent is to be run
	 */
	void runAgentControllers(final List<AgentController> controllers, final long agentRunDelay);

	/**
	 * Method runs single agent controller
	 *
	 * @param controller    controller that is to be run
	 * @param agentRunDelay delay after which the agent is to be run
	 */
	void runAgentController(final AgentController controller, final long agentRunDelay);

	/**
	 * Method used handle runnable execution termination
	 *
	 * @param executorService executor service that runs given process
	 * @param timeout         timeout value
	 * @param timeoutUnit     unit of timeout
	 */
	void shutdownAndAwaitTermination(final ExecutorService executorService,
			final int timeout,
			final TimeUnit timeoutUnit);
}
