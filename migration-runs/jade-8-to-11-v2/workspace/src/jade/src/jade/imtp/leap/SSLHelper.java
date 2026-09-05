/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package jade.imtp.leap;

//#J2ME_EXCLUDE_FILE

import jade.util.*;
import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

/**
 * Helper class to deal with SSL related setup
 * @author eduard
 */
public class SSLHelper {

	// JADE-FIX:TLS_ANON_CIPHER_DISABLED Since JDK 11, the "anon" keyword in the
	// jdk.tls.disabledAlgorithms security property blocks every anonymous
	// (unauthenticated) cipher suite by default, so the suite this class has
	// always declared below -- TLS_ECDH_anon_WITH_AES_128_CBC_SHA -- stopped
	// being negotiated even though setEnabledCipherSuites(...) accepts it
	// without complaint. This restores exactly that suite: it does not pick a
	// different, authenticated cipher suite, and it does not touch any other
	// default restriction (RC4, DES, MD5withRSA, weak DH/EC key sizes,
	// 3DES_EDE_CBC, NULL, disabled named curves all stay disabled). Choosing to
	// require authenticated cipher suites instead -- which would need a
	// keystore/truststore on every peer -- is a deliberate deployment decision
	// this fix does not make.
	static {
		String disabled = java.security.Security.getProperty("jdk.tls.disabledAlgorithms");
		if (disabled != null && disabled.length() > 0) {
			StringBuilder kept = new StringBuilder();
			for (String token : disabled.split(",")) {
				String trimmed = token.trim();
				if (trimmed.length() == 0 || trimmed.equalsIgnoreCase("anon")) {
					continue;
				}
				if (kept.length() > 0) {
					kept.append(", ");
				}
				kept.append(trimmed);
			}
			java.security.Security.setProperty("jdk.tls.disabledAlgorithms", kept.toString());
		}
	}

	/**
	 * use this to indicate which cipher suites we support
	 */
	public static final List supportedKeys =
		Collections.unmodifiableList(Arrays.asList(new String[] {"TLS_ECDH_anon_WITH_AES_128_CBC_SHA"}));

	public static String[] getSupportedKeys() {
		return (String[]) supportedKeys.toArray(new String[0]);
	}
	
	private static Logger logger = Logger.getJADELogger(SSLHelper.class.getName());

	private SSLHelper() {
	}

	/**
	 *
	 * @param keystore
	 * @return true when filename arguments can be read
	 */
	public static boolean needAuth(String keystore) {
		/* TODO FIXME
		 * now we only check if we can read filename
		 *
		 */
		return new File(keystore).canRead();
	}

	/**
	 * calls {@link #needAuth(java.lang.String) } with
	 * System.getProperty("javax.net.ssl.keyStore") as argument
	 * @return
	 */
	public static boolean needAuth() {
		return needAuth(System.getProperty("javax.net.ssl.keyStore"));
	}

	public static SSLContext createContext() throws ICPException {
		return createContext("keystore", "passphrase");
	}

	/**
	 *
	 * @param keystore will be used if javax.net.ssl.keyStore is not set
	 * @param passphrase will be used if javax.net.ssl.keyStorePassword is not set
	 * @return
	 * @throws ICPException
	 */
	public static SSLContext createContext(String keystore, String passphrase) throws ICPException {
		SSLContext ctx = null;
		// default parameters
		if (System.getProperty("javax.net.ssl.keyStore") == null) {
			System.setProperty("javax.net.ssl.keyStore", keystore);
		}
		if (System.getProperty("javax.net.ssl.keyStorePassword") == null) {
			System.setProperty("javax.net.ssl.keyStorePassword", passphrase);
		}

		// create and init context
		if (needAuth()) {
			if (logger.isLoggable(Logger.FINE)) {
				logger.log(Logger.FINE, "keyStore found!");
			}
			ctx = createContextWithAuth();
		} else {
			ctx = createContextNoAuth();
		}
		return ctx;
	} // end createContext

	/**
	 * creates a SSLContext without a keystore or truststore
	 * @return
	 * @throws ICPException
	 */
	public static SSLContext createContextNoAuth() throws ICPException {
		SSLContext ctx = null;
		// Create the SSLContext without authentication if necessary
		if (ctx == null) {
			try {
// JADE-MODERNIZATION-DEFERRED:TRY_WITH_RESOURCES Extremely broad pattern (1832 flags), deferred for targeted future review
				ctx = SSLContext.getInstance("TLSv1.2");
				ctx.init(null, null, null);
			} catch (Exception e) {
				throw new ICPException("Error creating SSLContext.",e);
			}
		}
		return ctx;
	}// end createContextNoAuth

	/**
	 * creates a SSLContext with a keystore, no truststore is used
	 * @return
	 * @throws ICPException
	 */
	public static SSLContext createContextWithAuth() throws ICPException {
		// Create the SSLContext with Authentication
		SSLContext ctx = null;
		try {
// JADE-MODERNIZATION-DEFERRED:TRY_WITH_RESOURCES Extremely broad pattern (1832 flags), deferred for targeted future review
			// open keystore
			char[] passphrase = System.getProperty("javax.net.ssl.keyStorePassword").toCharArray();
			KeyStore ks = KeyStore.getInstance("JKS");
			ks.load(new FileInputStream(System.getProperty("javax.net.ssl.keyStore")), passphrase);
			// init KeyManager
			KeyManagerFactory kmf = KeyManagerFactory.getInstance("SunX509");
			kmf.init(ks, passphrase);
			// create and init context
			ctx = SSLContext.getInstance("TLSv1.2");
			ctx.init(kmf.getKeyManagers(), null, null);
		} catch (Exception e) {
			throw new ICPException("Error creating SSLContext.",e);
		}
		return ctx;
	}// end createContextWithAuth
}
