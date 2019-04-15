import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext, DynamicFrame
from awsglue.job import Job
import pydevd

from pyspark.context import SparkContext
import os

from pyspark.sql import SparkSession

def dvdrental():
  pydevd.settrace('169.254.76.1', port=9001, stdoutToServer=True, stderrToServer=True)

  spark = SparkSession \
    .builder \
    .appName("DVD Rental") \
    .getOrCreate()

  rentalFileLoc= 's3://vg-simple-datalake/dvdrental/public/rental/LOAD00000001.csv'
  paymentFileLoc= 's3://vg-simple-datalake/dvdrental/public/payment/LOAD00000001.csv'
  customerFileLoc= 's3://vg-simple-datalake/dvdrental/public/customer/LOAD00000001.csv'
  s3OutputLoc = 's3://vgsimpledatalake/dvdrental/olap'

  rentaldf = spark.read.csv(rentalFileLoc, header= "true")
  customerdf = spark.read.csv(customerFileLoc, header= "true")
  paymentdf = spark.read.csv(paymentFileLoc, header= "true")

  rentaldf.createOrReplaceTempView("rental")
  customerdf.createOrReplaceTempView("customer")
  paymentdf.createOrReplaceTempView("payment")

  spark.sql("select c.store_id, date_format(to_date(r.rental_date), 'yyyy-MM-dd') rental_date, p.payment_date, p.amount " \
            "from rental r "  \
            "inner join payment p on r.rental_id = p.rental_id " \
            "inner join customer c on r.customer_id = c.customer_id " \
            "order by r.rental_id, r.rental_date").createOrReplaceTempView("customerRentalPayment")

  storeRental = spark.sql("select distinct store_id, rental_date from customerRentalPayment order by store_id, rental_date").collect()

  for r in storeRental:
    fileContent = spark.sql("select store_id, rental_date, payment_date, amount "
                            "from customerRentalPayment where store_id= " + r.store_id + " and rental_date= '" + r.rental_date + "'")
    fileContent.repartition(1)
    fileContent.write.parquet(s3OutputLoc)
    print "Writing %s-%s" % (r.store_id, r.rental_date)

def main():
  pydevd.settrace('169.254.76.1', port=9001, stdoutToServer=True, stderrToServer=True)

  glueContext = GlueContext(SparkContext.getOrCreate());

  rentalFileLoc= 's3://vg-simple-datalake/dvdrental/public/rental/LOAD00000001.csv'
  paymentFileLoc= 's3://vg-simple-datalake/dvdrental/public/payment/LOAD00000001.csv'
  customerFileLoc= 's3://vg-simple-datalake/dvdrental/public/customer/LOAD00000001.csv'

  rentalDataFrame = glueContext.read.format("csv").option(
     "header", "true").option(
     "inferSchema", "true").load(rentalFileLoc).withColumnRenamed('customer_id', 'rental_customer_id')
  # rentalDF = DynamicFrame.fromDF(rentalDataFrame, glueContext, "rentalDF").rename_field('customer_id', 'rental_customer_id')

  paymentDataFrame = glueContext.read.format("csv").option(
     "header", "true").option(
     "inferSchema", "true").load(paymentFileLoc).withColumnRenamed('rental_id', 'payment_rental_id')
  # paymentDF = DynamicFrame.fromDF(paymentDataFrame, glueContext, "paymentDF").drop_fields([""]).drop_fields(['rental_id'])

  customerDataFrame = glueContext.read.format("csv").option(
     "header", "true").option(
     "inferSchema", "true").load(customerFileLoc)
  # customerDF = DynamicFrame.fromDF(customerDataFrame, glueContext, "customerDF")

  # rentalPayment = Join.apply(rentalDataFrame, paymentDataFrame, "rental_id", "rental_id")
  # rentalPaymentCust = Join.apply(rentalPayment, customerDataFrame, "rental_customer_id", "customer_id")\
      #.orderBy("store_id", "rental_date")

  rentalPayment = rentalDataFrame.join(paymentDataFrame, rentalDataFrame.rental_id == paymentDataFrame.payment_rental_id ).withColumn("rental_date", rentalDataFrame.rental_date.cast('date') )
  rentalPaymentCust = rentalPayment.join(customerDataFrame, rentalPayment.rental_customer_id == customerDataFrame.customer_id ).orderBy("store_id", "rental_date")

  rentalPaymentCust.printSchema()
  # rentalPaymentCust.select('store_id', 'rental_id'].distinct().show()

  # rentalPaymentCustDyF = DynamicFrame.fromDF(rentalPaymentCust, glueContext, "rentalPaymentCust")
  storeRentalPrefix = rentalPaymentCust.select(['store_id', 'rental_date']).distinct().orderBy("store_id", "rental_date")
  storeRentalPrefixCnt = storeRentalPrefix.count()

  storePrefix = storeRentalPrefix.select('store_id').distinct().orderBy("store_id")
  storePrefixCnt = storePrefix.count()

  rentalPrefix = storeRentalPrefix.select('rental_date').distinct().orderBy("rental_date")
  rentalPrefixCnt = rentalPrefix.count()

  print("there are {} unique store_id-rental_id", storeRentalPrefixCnt)
  print("there are {} unique store_id", storePrefixCnt)
  print("there are {} unique rental_date", rentalPrefixCnt)

  storesList = storePrefix.rdd.map(lambda r:r[0]).collect()
  storesRentalsMap = storeRentalPrefix.rdd.collectAsMap()

  print(storesList)
  print(storesRentalsMap)

  print "length of storesRentalsMap %d" % len(storesRentalsMap)

if __name__ == "__main__":
  dvdrental()
