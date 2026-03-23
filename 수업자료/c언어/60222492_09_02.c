#include <stdio.h>
void main(){
	int num,sum,i;
	sum = 0;
	printf("양의 정수를 1개 입력하시오: ");
	scanf("%d",&num);
	for(i=1;i<=num;i++)
	 {
	 sum = sum+i;}
	 printf("1부터 사용자가 입력한 정수까지의 합:%d",sum);
}
