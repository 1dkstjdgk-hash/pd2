#include <stdio.h>
void main(){
	int i=1;
	int sum=0,num;
	printf("정수를 입력하시오:");
	scanf("%d",&num);
	
	while(i<=num){
		if(i%2==0){
			sum+=i;
		}i++;
	}printf("짝수의 총합:%d",sum);
}
