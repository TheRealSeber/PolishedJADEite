package org.jrba.utils.file;

import static java.io.File.separator;
import static java.lang.String.join;
import static java.util.Arrays.stream;
import static java.util.Collections.emptyList;
import static java.util.Optional.ofNullable;
import static org.apache.commons.io.FileUtils.copyInputStreamToFile;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.stream.Stream;

import org.jrba.exception.InvalidFileException;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

import com.google.common.annotations.VisibleForTesting;

/**
 * Class with method that allow to parse the indicated file
 */
public class FileReader {

	/**
	 * Method reads a file from a selected path.
	 *
	 * @param filePath path to the file
	 * @return File
	 */
	public static File readFile(final String filePath) {
		try (InputStream inputStream = FileReader.class.getClassLoader().getResourceAsStream(filePath)) {
			final File tempFile = File.createTempFile("test", ".txt");
			copyInputStreamToFile(ofNullable(inputStream).orElseThrow(), tempFile);
			return tempFile;
		} catch (IOException | NullPointerException | NoSuchElementException e) {
			throw new InvalidFileException("Invalid file name.");
		}
	}

	/**
	 * Method copies and returns given file.
	 *
	 * @param file file
	 * @return File
	 */
	public static File readFile(final File file) {
		try {
			final File tempFile = File.createTempFile("test_" + file.getName(), ".txt");
			copyInputStreamToFile(new FileInputStream(file), tempFile);
			return tempFile;
		} catch (IOException | NullPointerException e) {
			throw new InvalidFileException("File could not be read.");
		}
	}

	/**
	 * Method reads files from a selected path
	 *
	 * @param filesPath path to the files
	 * @return File
	 */
	public static List<File> readAllFiles(final String filesPath) {
		final PathMatchingResourcePatternResolver patternResolver = new PathMatchingResourcePatternResolver(
				FileReader.class.getClassLoader());

		try {
			final Resource[] resources = patternResolver.getResources(filesPath);
			return resources.length == 0 ?
					emptyList() :
					stream(resources)
							.map(FileReader::listResourceFiles)
							.flatMap(Stream::of)
							.filter(File::isFile)
							.map(FileReader::readFile)
							.toList();
		} catch (Exception e) {
			return emptyList();
		}
	}

	/**
	 * Method verifies if the system was started from the JAR or IDE
	 *
	 * @return boolean indicating if the system was started from jar
	 */
	public static boolean isLoadedInJar() {
		final String classPath = FileReader.class.getProtectionDomain().getCodeSource().getLocation().getPath();
		return classPath.endsWith(".jar");
	}

	/**
	 * Method builds correct path of the given resource file
	 *
	 * @param pathElements elements of the path
	 * @return String path to the resource
	 */
	public static String buildResourceFilePath(final String... pathElements) {
		if (isLoadedInJar()) {
			return join("/", pathElements);
		}
		return join(separator, pathElements);
	}

	private static File[] listResourceFiles(final Resource resource) {
		try {
			return resource.getFile().listFiles();
		} catch (IOException e) {
			throw new InvalidFileException("File could not be read.");
		}
	}
}
