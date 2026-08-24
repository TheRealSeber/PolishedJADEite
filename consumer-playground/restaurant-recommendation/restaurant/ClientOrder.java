package restaurant;

import java.io.Serializable;
import java.util.Map;

public class ClientOrder implements Serializable {
    private final String orderId;
    private final String cuisine;
    private final String dish;
    private final double maxPrice;
    private final String deliveryZone;
    private final Map<String, Object> additionalInstructions;

    public ClientOrder(String orderId, String cuisine, String dish, double maxPrice,
                       String deliveryZone, Map<String, Object> additionalInstructions) {
        this.orderId = orderId;
        this.cuisine = cuisine;
        this.dish = dish;
        this.maxPrice = maxPrice;
        this.deliveryZone = deliveryZone;
        this.additionalInstructions = additionalInstructions;
    }

    public String getOrderId() { return orderId; }
    public String getCuisine() { return cuisine; }
    public String getDish() { return dish; }
    public double getMaxPrice() { return maxPrice; }
    public String getDeliveryZone() { return deliveryZone; }
    public Map<String, Object> getAdditionalInstructions() { return additionalInstructions; }
}