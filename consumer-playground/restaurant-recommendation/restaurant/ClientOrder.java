package restaurant;

import java.io.Serializable;
import java.util.Map;

public class ClientOrder implements Serializable {
    private final String cuisine;
    private final String dish;
    private final double maxPrice;
    private final Map<String, Object> additionalInstructions;

    public ClientOrder(String cuisine, String dish, double maxPrice, Map<String, Object> additionalInstructions) {
        this.cuisine = cuisine;
        this.dish = dish;
        this.maxPrice = maxPrice;
        this.additionalInstructions = additionalInstructions;
    }

    public String getCuisine() { return cuisine; }
    public String getDish() { return dish; }
    public double getMaxPrice() { return maxPrice; }
    public Map<String, Object> getAdditionalInstructions() { return additionalInstructions; }
}
